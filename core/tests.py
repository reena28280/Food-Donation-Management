from datetime import timedelta
from io import BytesIO
from io import StringIO
import tempfile
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from accounts.models import Profile
from donations.models import FoodDonation
from donations.models import FoodCategory
from foodrequests.models import DonationRequest
from logistics.models import CollectionRecord, VolunteerAssignment
from core.models import Notification
from PIL import Image
from core.models import ContactEnquiry


class NourishLoopWorkflowTests(TestCase):
	def setUp(self):
		self.donor = self.create_user('donor', 'DONOR')
		self.receiver = self.create_user('receiver', 'RECEIVER')
		self.volunteer = self.create_user('volunteer', 'VOLUNTEER')
		now = timezone.now()
		self.donation = FoodDonation.objects.create(
			donor=self.donor,
			title='Community lunch',
			description='Freshly prepared lunch portions.',
			food_type='VEG',
			total_servings=2,
			prepared_at=now - timedelta(hours=1),
			pickup_deadline=now + timedelta(days=1),
			pickup_address='12 Market Street',
			city='Springfield',
			packaging_confirmed=True,
			storage_confirmed=True,
		)

	def create_user(self, username, role):
		user = User.objects.create_user(username=username, password='local-test-password')
		Profile.objects.create(
			user=user,
			role=role,
			verification_status='APPROVED',
			phone='555-0123',
			address='12 Market Street',
			city='Springfield',
		)
		return user

	def request_all_servings(self):
		self.client.force_login(self.receiver)
		return self.client.post(reverse('request_create', args=[self.donation.pk]), {
			'requested_servings': 2,
			'message': 'We can collect this afternoon.',
		})

	def create_accepted_request(self, receiver=None, servings=1):
		receiver = receiver or self.receiver
		food_request = DonationRequest.objects.create(
			donation=self.donation,
			receiver=receiver,
			requested_servings=servings,
			status='ACCEPTED',
		)
		self.donation.refresh_from_db()
		self.donation.reserved_servings += servings
		self.donation.status = 'FULL' if self.donation.remaining_servings == 0 else 'AVAILABLE'
		self.donation.save(update_fields=['reserved_servings', 'status'])
		return food_request

	def confirm_handoff_as_both_parties(self, food_request):
		self.client.force_login(food_request.receiver)
		self.client.post(reverse('confirm_collection', args=[food_request.pk]))
		self.client.force_login(self.donor)
		self.client.post(reverse('confirm_collection', args=[food_request.pk]))

	def donation_form_data(self, title='Fresh surplus meal'):
		now = timezone.localtime()
		return {
			'title': title,
			'description': 'Freshly prepared portions for local pickup.',
			'category': '',
			'food_type': 'VEG',
			'total_servings': '4',
			'prepared_at': (now - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),
			'pickup_deadline': (now + timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M'),
			'pickup_address': 'Private kitchen, 12 Market Street',
			'city': 'Springfield',
			'allergens': 'Contains dairy',
			'storage_details': 'Kept refrigerated',
			'packaging_confirmed': 'on',
			'storage_confirmed': 'on',
		}

	def test_pending_donor_cannot_create_donation(self):
		self.donor.profile.verification_status = 'PENDING'
		self.donor.profile.save(update_fields=['verification_status'])
		self.client.force_login(self.donor)
		response = self.client.post(reverse('donation_create'), self.donation_form_data())
		self.assertEqual(response.status_code, 302)
		self.assertEqual(FoodDonation.objects.count(), 1)

	def test_approved_donor_can_create_donation(self):
		self.client.force_login(self.donor)
		response = self.client.post(reverse('donation_create'), self.donation_form_data())
		self.assertEqual(response.status_code, 302)
		donation = FoodDonation.objects.get(title='Fresh surplus meal', donor=self.donor)
		self.assertEqual(donation.total_servings, 4)
		self.assertEqual(donation.city, 'Springfield')
		self.assertEqual(donation.pickup_address, 'Private kitchen, 12 Market Street')
		self.assertTrue(donation.packaging_confirmed)
		self.assertTrue(donation.storage_confirmed)

	def test_donation_create_accepts_a_valid_food_image(self):
		image_data = BytesIO()
		Image.new('RGB', (4, 4), color='green').save(image_data, format='PNG')
		image_data.seek(0)
		payload = self.donation_form_data(title='Meal with photo')
		payload['image'] = SimpleUploadedFile('meal.png', image_data.read(), content_type='image/png')
		self.client.force_login(self.donor)
		with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
			response = self.client.post(reverse('donation_create'), payload)
			self.assertEqual(response.status_code, 302)
			donation = FoodDonation.objects.get(title='Meal with photo')
			self.assertTrue(donation.image.name.endswith('.png'))

	def test_donation_create_rejects_invalid_image(self):
		payload = self.donation_form_data(title='Invalid photo')
		payload['image'] = SimpleUploadedFile('not-image.png', b'not an image', content_type='image/png')
		self.client.force_login(self.donor)
		response = self.client.post(reverse('donation_create'), payload)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Upload a valid JPEG, PNG, or WebP image.', status_code=200)
		self.assertFalse(FoodDonation.objects.filter(title='Invalid photo').exists())

	def test_donation_create_rejects_zero_servings(self):
		payload = self.donation_form_data(title='Zero serving food')
		payload['total_servings'] = '0'
		self.client.force_login(self.donor)
		response = self.client.post(reverse('donation_create'), payload)
		self.assertEqual(response.status_code, 200)
		self.assertFalse(FoodDonation.objects.filter(title='Zero serving food').exists())

	def test_donation_create_rejects_deadline_before_preparation(self):
		payload = self.donation_form_data(title='Invalid timing')
		payload['pickup_deadline'] = (timezone.localtime() - timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M')
		self.client.force_login(self.donor)
		response = self.client.post(reverse('donation_create'), payload)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Pickup deadline must be in the future')
		self.assertFalse(FoodDonation.objects.filter(title='Invalid timing').exists())

	def test_donation_create_requires_safety_confirmations(self):
		payload = self.donation_form_data(title='Unconfirmed food')
		payload.pop('packaging_confirmed')
		payload.pop('storage_confirmed')
		self.client.force_login(self.donor)
		response = self.client.post(reverse('donation_create'), payload)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Confirm the food is packed safely')
		self.assertContains(response, 'Confirm the storage information is accurate')
		self.assertFalse(FoodDonation.objects.filter(title='Unconfirmed food').exists())

	def test_donor_can_edit_an_unreserved_listing(self):
		self.client.force_login(self.donor)
		payload = self.donation_form_data(title='Updated lunch title')
		payload['total_servings'] = '6'
		response = self.client.post(reverse('donation_edit', args=[self.donation.pk]), payload)
		self.assertEqual(response.status_code, 302)
		self.donation.refresh_from_db()
		self.assertEqual(self.donation.title, 'Updated lunch title')
		self.assertEqual(self.donation.total_servings, 6)

	def test_donor_cannot_edit_listing_with_reserved_servings(self):
		self.create_accepted_request(servings=1)
		self.client.force_login(self.donor)
		payload = self.donation_form_data(title='Should not replace reserved listing')
		payload['total_servings'] = '10'
		response = self.client.post(reverse('donation_edit', args=[self.donation.pk]), payload)
		self.assertEqual(response.status_code, 302)
		self.donation.refresh_from_db()
		self.assertEqual(self.donation.title, 'Community lunch')
		self.assertEqual(self.donation.total_servings, 2)
		self.assertEqual(self.donation.reserved_servings, 1)

	def test_donor_close_cancels_pending_and_releases_servings_once(self):
		self.request_all_servings()
		food_request = DonationRequest.objects.get(donation=self.donation)
		self.client.force_login(self.donor)
		close_url = reverse('donation_cancel', args=[self.donation.pk])
		first_response = self.client.post(close_url)
		second_response = self.client.post(close_url)
		self.assertEqual(first_response.status_code, 302)
		self.assertEqual(second_response.status_code, 302)
		self.donation.refresh_from_db()
		food_request.refresh_from_db()
		self.assertEqual(self.donation.status, 'CANCELLED')
		self.assertEqual(self.donation.reserved_servings, 0)
		self.assertEqual(food_request.status, 'CANCELLED')

	def test_donor_listing_workspace_keeps_closed_donations_visible(self):
		self.donation.status = 'CANCELLED'
		self.donation.save(update_fields=['status'])
		self.client.force_login(self.donor)
		response = self.client.get(reverse('donation_list'), {'mine': '1'})
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.donation.title)
		self.assertContains(response, 'Cancelled')

	def test_pending_receiver_cannot_request_food(self):
		self.receiver.profile.verification_status = 'PENDING'
		self.receiver.profile.save(update_fields=['verification_status'])
		self.client.force_login(self.receiver)
		response = self.client.post(reverse('request_create', args=[self.donation.pk]), {'requested_servings': 1})
		self.assertEqual(response.status_code, 302)
		self.assertFalse(DonationRequest.objects.filter(donation=self.donation).exists())
		self.donation.refresh_from_db()
		self.assertEqual(self.donation.reserved_servings, 0)

	def test_approved_receiver_can_request_food(self):
		response = self.request_all_servings()
		self.assertEqual(response.status_code, 302)
		self.donation.refresh_from_db()
		self.assertEqual(self.donation.reserved_servings, 2)
		self.assertEqual(DonationRequest.objects.filter(donation=self.donation).count(), 1)
		self.assertTrue(Notification.objects.filter(user=self.donor, message__contains='requested 2 servings').exists())

	def test_multiple_receivers_reserve_independently_and_donor_can_review(self):
		second_receiver = self.create_user('second-receiver-request', 'RECEIVER')
		self.client.force_login(self.receiver)
		self.client.post(reverse('request_create', args=[self.donation.pk]), {
			'requested_servings': 1,
			'message': 'We can collect this afternoon.',
		})
		first_request = DonationRequest.objects.get(receiver=self.receiver, donation=self.donation)
		self.client.force_login(second_receiver)
		self.client.post(reverse('request_create', args=[self.donation.pk]), {
			'requested_servings': 1,
			'message': '',
		})
		second_request = DonationRequest.objects.get(receiver=second_receiver, donation=self.donation)
		self.donation.refresh_from_db()
		self.assertEqual(self.donation.reserved_servings, 2)
		self.assertEqual(self.donation.status, 'FULL')
		self.assertEqual(first_request.status, 'PENDING')
		self.assertEqual(second_request.status, 'PENDING')
		self.assertEqual(first_request.message, 'We can collect this afternoon.')
		self.assertEqual(second_request.message, '')
		self.assertEqual(Notification.objects.filter(user=self.donor).count(), 2)

		self.client.force_login(self.donor)
		response = self.client.get(reverse('my_requests'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Incoming requests')
		self.assertContains(response, 'Accept')
		self.assertContains(response, 'Decline')
		self.assertContains(response, 'We can collect this afternoon.')

		self.client.post(reverse('request_decision', args=[first_request.pk, 'accept']))
		first_request.refresh_from_db()
		self.donation.refresh_from_db()
		self.assertEqual(first_request.status, 'ACCEPTED')
		self.assertEqual(self.donation.reserved_servings, 2)
		self.assertTrue(Notification.objects.filter(user=self.receiver, message__contains='was accepted').exists())

		self.client.post(reverse('request_decision', args=[second_request.pk, 'reject']))
		second_request.refresh_from_db()
		self.donation.refresh_from_db()
		self.assertEqual(second_request.status, 'REJECTED')
		self.assertEqual(self.donation.reserved_servings, 1)
		self.assertEqual(self.donation.status, 'AVAILABLE')
		self.assertTrue(Notification.objects.filter(user=second_receiver, message__contains='was declined').exists())

	def test_receiver_cancellation_notifies_donor_and_releases_once(self):
		self.request_all_servings()
		food_request = DonationRequest.objects.get(donation=self.donation)
		self.client.force_login(self.receiver)
		cancel_url = reverse('request_cancel', args=[food_request.pk])
		self.client.post(cancel_url)
		self.client.post(cancel_url)
		self.donation.refresh_from_db()
		self.assertEqual(self.donation.reserved_servings, 0)
		self.assertEqual(Notification.objects.filter(user=self.donor, message__contains='cancelled their request').count(), 1)

	def test_notification_inbox_count_is_user_scoped_and_mark_read_is_post_only(self):
		notification = Notification.objects.create(user=self.receiver, message='Your request was accepted.')
		Notification.objects.create(user=self.donor, message='Other user update.')
		self.client.force_login(self.receiver)
		response = self.client.get(reverse('notification_list'))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context['unread_count'], 1)
		self.assertContains(response, 'Your request was accepted.')
		self.assertNotContains(response, 'Other user update.')
		self.client.get(reverse('notification_mark_read', args=[notification.pk]))
		notification.refresh_from_db()
		self.assertFalse(notification.is_read)
		self.client.post(reverse('notification_mark_read', args=[notification.pk]))
		notification.refresh_from_db()
		self.assertTrue(notification.is_read)
		self.assertEqual(self.client.get(reverse('notification_list')).context['unread_count'], 0)
		other_user_notification = Notification.objects.create(user=self.donor, message='Private donor update.')
		self.client.post(reverse('notification_mark_read', args=[other_user_notification.pk]))
		other_user_notification.refresh_from_db()
		self.assertFalse(other_user_notification.is_read)

	def create_staff_user(self, username='staff-user'):
		return User.objects.create_user(username=username, password='local-test-password', is_staff=True)

	def test_staff_dashboard_is_staff_only_and_shows_database_counts(self):
		self.create_accepted_request(servings=1)
		self.client.force_login(self.donor)
		response = self.client.get(reverse('staff_dashboard'))
		self.assertEqual(response.status_code, 302)
		self.assertEqual(response['Location'], f"{reverse('login')}?next={reverse('staff_dashboard')}")

		self.client.force_login(self.create_staff_user())
		response = self.client.get(reverse('staff_dashboard'))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context['stats']['total_users'], 3)
		self.assertEqual(response.context['stats']['donors'], 1)
		self.assertEqual(response.context['stats']['receivers'], 1)
		self.assertEqual(response.context['stats']['volunteers'], 1)
		self.assertEqual(response.context['stats']['donations'], 1)
		self.assertEqual(response.context['stats']['requests'], 1)

	def test_staff_can_manage_users_categories_donations_and_requests(self):
		staff = User.objects.create_superuser(
			username='admin-manager',
			email='admin@example.com',
			password='local-test-password',
		)
		self.client.force_login(staff)
		for url_name in [
			'admin:auth_user_changelist',
			'admin:donations_foodcategory_changelist',
			'admin:donations_fooddonation_changelist',
			'admin:foodrequests_donationrequest_changelist',
		]:
			with self.subTest(url_name=url_name):
				response = self.client.get(reverse(url_name))
				self.assertEqual(response.status_code, 200)

	def test_staff_can_approve_and_reject_pending_organizations(self):
		second_donor = self.create_user('pending-donor', 'DONOR')
		self.donor.profile.verification_status = 'PENDING'
		self.donor.profile.save(update_fields=['verification_status'])
		second_donor.profile.verification_status = 'PENDING'
		second_donor.profile.save(update_fields=['verification_status'])
		staff = self.create_staff_user()
		self.client.force_login(staff)
		queue = self.client.get(reverse('staff_verification'))
		self.assertEqual(queue.status_code, 200)
		self.assertContains(queue, self.donor.username)
		self.client.post(reverse('staff_verify_profile', args=[self.donor.profile.pk, 'approve']))
		self.client.post(reverse('staff_verify_profile', args=[second_donor.profile.pk, 'reject']))
		self.donor.profile.refresh_from_db()
		second_donor.profile.refresh_from_db()
		self.assertEqual(self.donor.profile.verification_status, 'APPROVED')
		self.assertEqual(second_donor.profile.verification_status, 'REJECTED')
		self.assertEqual(Notification.objects.filter(user=self.donor).count(), 0)

	def test_non_staff_cannot_verify_profiles_or_download_reports(self):
		self.client.force_login(self.donor)
		for url_name in ['staff_dashboard', 'staff_verification', 'staff_reports', 'staff_reports_csv']:
			response = self.client.get(reverse(url_name))
			self.assertIn(response.status_code, [302, 403])
		response = self.client.post(reverse('staff_verify_profile', args=[self.receiver.profile.pk, 'approve']))
		self.assertIn(response.status_code, [302, 403])
		self.receiver.profile.refresh_from_db()
		self.assertEqual(self.receiver.profile.verification_status, 'APPROVED')

	def test_staff_reports_show_monthly_metrics_and_csv_download(self):
		food_request = self.create_accepted_request(servings=1)
		food_request.status = 'COMPLETED'
		food_request.save(update_fields=['status'])
		self.client.force_login(self.create_staff_user())
		response = self.client.get(reverse('staff_reports'))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context['stats']['completed_collections'], 1)
		self.assertEqual(response.context['monthly_activity'][0]['donations'], 1)
		csv_response = self.client.get(reverse('staff_reports_csv'))
		self.assertEqual(csv_response.status_code, 200)
		self.assertEqual(csv_response['Content-Type'], 'text/csv; charset=utf-8')
		self.assertIn(b'Monthly activity', csv_response.content)
		self.assertIn(b'Completed Collections', csv_response.content)

	def test_receiver_history_renders_pending_request_without_assignment(self):
		self.request_all_servings()
		response = self.client.get(reverse('my_requests'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Your food requests')
		self.assertContains(response, 'Pending')
		self.assertContains(response, 'Cancel request')

	def test_account_without_profile_can_complete_profile_instead_of_getting_404(self):
		account = User.objects.create_user(username='legacy-member', password='local-test-password')
		self.client.force_login(account)

		response = self.client.get(reverse('profile'))

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.context['is_profile_setup'])
		self.assertContains(response, 'Complete your profile')

		response = self.client.post(reverse('profile'), {
			'first_name': 'Legacy',
			'last_name': 'Member',
			'email': 'legacy@example.com',
			'role': 'RECEIVER',
			'organization_type': 'NGO',
			'organization_name': 'Community Support',
			'phone': '555-0190',
			'address': '45 Oak Avenue',
			'city': 'Springfield',
		})

		self.assertRedirects(response, reverse('dashboard'))
		profile = Profile.objects.get(user=account)
		self.assertEqual(profile.role, 'RECEIVER')
		self.assertEqual(profile.verification_status, 'PENDING')
		account.refresh_from_db()
		self.assertEqual(account.first_name, 'Legacy')
		self.assertEqual(account.email, 'legacy@example.com')

	def test_donor_dashboard_can_accept_and_reject_received_requests(self):
		second_receiver = self.create_user('second-dashboard-receiver', 'RECEIVER')
		first_request = DonationRequest.objects.create(
			donation=self.donation,
			receiver=self.receiver,
			requested_servings=1,
		)
		second_request = DonationRequest.objects.create(
			donation=self.donation,
			receiver=second_receiver,
			requested_servings=1,
		)
		self.donation.reserved_servings = 2
		self.donation.status = 'FULL'
		self.donation.save(update_fields=['reserved_servings', 'status'])

		self.client.force_login(self.donor)
		dashboard = self.client.get(reverse('dashboard'))
		self.assertEqual(dashboard.status_code, 200)
		self.assertContains(dashboard, 'Received Requests')
		self.assertContains(dashboard, self.receiver.username)
		self.assertContains(dashboard, self.donation.title)
		self.assertContains(dashboard, '1 servings')
		self.assertContains(dashboard, 'Accept')
		self.assertContains(dashboard, 'Reject')

		response = self.client.post(reverse('request_decision', args=[first_request.pk, 'accept']), {
			'return_to': 'dashboard',
		})
		self.assertRedirects(response, reverse('dashboard'))
		first_request.refresh_from_db()
		self.assertEqual(first_request.status, 'ACCEPTED')
		self.assertTrue(Notification.objects.filter(
			user=self.receiver,
			message__contains='was accepted',
		).exists())

		response = self.client.post(reverse('request_decision', args=[second_request.pk, 'reject']), {
			'return_to': 'dashboard',
		})
		self.assertRedirects(response, reverse('dashboard'))
		second_request.refresh_from_db()
		self.donation.refresh_from_db()
		self.assertEqual(second_request.status, 'REJECTED')
		self.assertEqual(self.donation.reserved_servings, 1)
		self.assertEqual(self.donation.status, 'AVAILABLE')
		self.assertTrue(Notification.objects.filter(
			user=second_receiver,
			message__contains='was declined',
		).exists())

		self.client.force_login(self.receiver)
		receiver_dashboard = self.client.get(reverse('dashboard'))
		self.assertContains(receiver_dashboard, 'My Requests')
		self.assertContains(receiver_dashboard, 'Accepted')
		self.assertEqual(receiver_dashboard.context['stats']['accepted'], 1)

		self.client.force_login(second_receiver)
		rejected_dashboard = self.client.get(reverse('dashboard'))
		self.assertContains(rejected_dashboard, 'My Requests')
		self.assertContains(rejected_dashboard, 'Rejected')
		self.assertEqual(rejected_dashboard.context['stats']['rejected'], 1)

	def test_receiver_dashboard_displays_all_request_statuses(self):
		for status in ['PENDING', 'ACCEPTED', 'REJECTED', 'COMPLETED']:
			DonationRequest.objects.create(
				donation=self.donation,
				receiver=self.receiver,
				requested_servings=1,
				status=status,
			)

		self.client.force_login(self.receiver)
		response = self.client.get(reverse('dashboard'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'My Requests')
		for status in ['Pending', 'Accepted', 'Rejected', 'Completed']:
			with self.subTest(status=status):
				self.assertContains(response, status)
		self.assertEqual(response.context['stats']['pending'], 1)
		self.assertEqual(response.context['stats']['accepted'], 1)
		self.assertEqual(response.context['stats']['rejected'], 1)
		self.assertEqual(response.context['stats']['completed'], 1)

	def test_pending_volunteer_cannot_claim_delivery(self):
		food_request = self.create_accepted_request()
		self.volunteer.profile.verification_status = 'PENDING'
		self.volunteer.profile.save(update_fields=['verification_status'])
		self.client.force_login(self.volunteer)
		response = self.client.post(reverse('claim_delivery', args=[food_request.pk]))
		self.assertEqual(response.status_code, 302)
		self.assertFalse(VolunteerAssignment.objects.filter(request=food_request).exists())

	def test_approved_volunteer_can_claim_delivery(self):
		food_request = self.create_accepted_request()
		self.client.force_login(self.volunteer)
		response = self.client.post(reverse('claim_delivery', args=[food_request.pk]))
		self.assertEqual(response.status_code, 302)
		self.assertTrue(VolunteerAssignment.objects.filter(request=food_request, volunteer=self.volunteer).exists())

	def test_donor_dashboard_statistics_use_database_counts(self):
		self.create_accepted_request(servings=1)
		self.client.force_login(self.donor)
		response = self.client.get(reverse('dashboard'))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context['stats'], {
			'total_donations': 1,
			'active_listings': 1,
			'requests': 1,
			'completed': 0,
		})

	def test_receiver_dashboard_statistics_use_database_counts(self):
		self.request_all_servings()
		self.client.force_login(self.receiver)
		response = self.client.get(reverse('dashboard'))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context['stats'], {
			'requests': 1,
			'pending': 1,
			'accepted': 0,
			'rejected': 0,
			'completed': 0,
		})

	def test_volunteer_dashboard_groups_available_assigned_and_completed(self):
		available_request = self.create_accepted_request(receiver=self.receiver, servings=1)
		completed_receiver = self.create_user('completed-receiver', 'RECEIVER')
		completed_request = self.create_accepted_request(receiver=completed_receiver, servings=1)
		VolunteerAssignment.objects.create(request=completed_request, volunteer=self.volunteer, status='DELIVERED')
		completed_request.status = 'COMPLETED'
		completed_request.save(update_fields=['status'])
		self.client.force_login(self.volunteer)
		response = self.client.get(reverse('dashboard'))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context['stats'], {'available': 1, 'assigned': 0, 'completed': 1})
		self.assertQuerySetEqual(response.context['available_tasks'], [available_request])
		self.assertQuerySetEqual(response.context['completed_tasks'].values_list('request_id', flat=True), [completed_request.pk])

	def test_volunteer_claim_and_updates_show_task_groups(self):
		food_request = self.create_accepted_request()
		self.client.force_login(self.volunteer)
		self.client.post(reverse('claim_delivery', args=[food_request.pk]))
		self.assertTrue(Notification.objects.filter(user=self.volunteer, message__contains='Delivery assigned').exists())
		response = self.client.get(reverse('dashboard'))
		self.assertEqual(response.context['stats']['assigned'], 1)
		assignment = VolunteerAssignment.objects.get(request=food_request)
		self.client.post(reverse('update_delivery', args=[assignment.pk, 'PICKED_UP']))
		self.client.post(reverse('update_delivery', args=[assignment.pk, 'DELIVERED']))
		self.client.force_login(self.receiver)
		self.client.post(reverse('confirm_collection', args=[food_request.pk]))
		self.client.force_login(self.donor)
		self.client.post(reverse('confirm_collection', args=[food_request.pk]))
		self.client.post(reverse('confirm_collection', args=[food_request.pk]))
		self.client.force_login(self.volunteer)
		response = self.client.get(reverse('dashboard'))
		self.assertEqual(response.context['stats'], {'available': 0, 'assigned': 0, 'completed': 1})
		self.assertEqual(Notification.objects.filter(user__in=[self.receiver, self.donor, self.volunteer], message__contains='collection').count(), 3)
		self.assertEqual(Notification.objects.filter(user=self.volunteer, message__contains='Delivery assigned').count(), 1)

	def test_staff_user_is_kept_out_of_member_actions(self):
		self.donor.is_staff = True
		self.donor.save(update_fields=['is_staff'])
		self.client.force_login(self.donor)
		response = self.client.post(reverse('donation_create'), self.donation_form_data())
		self.assertRedirects(response, reverse('admin:index'))
		self.assertEqual(FoodDonation.objects.count(), 1)

	def test_rejected_members_cannot_use_restricted_actions(self):
		self.donor.profile.verification_status = 'REJECTED'
		self.donor.profile.save(update_fields=['verification_status'])
		self.client.force_login(self.donor)
		self.client.post(reverse('donation_create'), self.donation_form_data())
		self.assertEqual(FoodDonation.objects.count(), 1)

		self.receiver.profile.verification_status = 'REJECTED'
		self.receiver.profile.save(update_fields=['verification_status'])
		self.client.force_login(self.receiver)
		self.client.post(reverse('request_create', args=[self.donation.pk]), {'requested_servings': 1})
		self.assertFalse(DonationRequest.objects.filter(donation=self.donation).exists())

		food_request = self.create_accepted_request()
		self.volunteer.profile.verification_status = 'REJECTED'
		self.volunteer.profile.save(update_fields=['verification_status'])
		self.client.force_login(self.volunteer)
		self.client.post(reverse('claim_delivery', args=[food_request.pk]))
		self.assertFalse(VolunteerAssignment.objects.filter(request=food_request).exists())

	def test_signup_rejects_organization_type_incompatible_with_role(self):
		data = {
			'username': 'badreceiver',
			'first_name': 'Casey',
			'last_name': 'Test',
			'email': 'casey@example.com',
			'password1': 'NourishLoop!2026',
			'password2': 'NourishLoop!2026',
			'role': 'RECEIVER',
			'organization_type': 'RESTAURANT',
			'phone': '555-0188',
			'address': '45 Oak Avenue',
			'city': 'Springfield',
		}
		response = self.client.post(reverse('signup'), data)
		self.assertEqual(response.status_code, 200)
		self.assertFalse(User.objects.filter(username='badreceiver').exists())
		self.assertContains(response, 'matches your account role')

	def test_public_detail_hides_full_pickup_address(self):
		response = self.client.get(reverse('donation_detail', args=[self.donation.pk]))
		self.assertEqual(response.status_code, 200)
		self.assertNotContains(response, self.donation.pickup_address)
		self.assertContains(response, self.donation.city)

	def test_donor_can_see_own_full_pickup_address(self):
		self.client.force_login(self.donor)
		response = self.client.get(reverse('donation_detail', args=[self.donation.pk]))
		self.assertContains(response, self.donation.pickup_address)

	def test_accepted_receiver_can_see_full_pickup_address(self):
		self.create_accepted_request()
		self.client.force_login(self.receiver)
		response = self.client.get(reverse('donation_detail', args=[self.donation.pk]))
		self.assertContains(response, self.donation.pickup_address)

	def test_assigned_volunteer_can_see_full_pickup_address(self):
		food_request = self.create_accepted_request()
		VolunteerAssignment.objects.create(request=food_request, volunteer=self.volunteer)
		self.client.force_login(self.volunteer)
		response = self.client.get(reverse('donation_detail', args=[self.donation.pk]))
		self.assertContains(response, self.donation.pickup_address)

	def test_unassigned_volunteer_sees_general_location_only(self):
		self.create_accepted_request()
		self.client.force_login(self.volunteer)
		response = self.client.get(reverse('delivery_board'))
		self.assertEqual(response.status_code, 200)
		self.assertNotContains(response, self.donation.pickup_address)
		self.assertContains(response, self.donation.city)

	def test_rejected_request_releases_reserved_servings_only_once(self):
		self.request_all_servings()
		food_request = DonationRequest.objects.get(donation=self.donation)
		self.client.force_login(self.donor)
		self.client.post(reverse('request_decision', args=[food_request.pk, 'reject']))
		self.client.post(reverse('request_decision', args=[food_request.pk, 'reject']))
		self.donation.refresh_from_db()
		self.assertEqual(self.donation.reserved_servings, 0)
		self.assertEqual(food_request.__class__.objects.get(pk=food_request.pk).status, 'REJECTED')

	def test_cancelled_request_releases_reserved_servings_only_once(self):
		self.request_all_servings()
		food_request = DonationRequest.objects.get(donation=self.donation)
		self.client.force_login(self.receiver)
		self.client.post(reverse('request_cancel', args=[food_request.pk]))
		self.client.post(reverse('request_cancel', args=[food_request.pk]))
		self.donation.refresh_from_db()
		food_request.refresh_from_db()
		self.assertEqual(self.donation.reserved_servings, 0)
		self.assertEqual(food_request.status, 'CANCELLED')

	def test_overbooking_is_rejected(self):
		self.request_all_servings()
		other_receiver = self.create_user('other-receiver', 'RECEIVER')
		self.client.force_login(other_receiver)
		self.client.post(reverse('request_create', args=[self.donation.pk]), {'requested_servings': 1})
		self.donation.refresh_from_db()
		self.assertEqual(self.donation.reserved_servings, 2)
		self.assertEqual(DonationRequest.objects.filter(donation=self.donation).count(), 1)

	def test_only_authorized_users_can_confirm_collection(self):
		food_request = self.create_accepted_request()
		VolunteerAssignment.objects.create(request=food_request, volunteer=self.volunteer, status='DELIVERED')
		record = CollectionRecord.objects.create(request=food_request)
		stranger = self.create_user('stranger', 'RECEIVER')
		self.client.force_login(stranger)
		self.client.post(reverse('confirm_collection', args=[food_request.pk]))
		record.refresh_from_db()
		self.assertFalse(record.receiver_confirmed)
		self.assertFalse(record.donor_confirmed)

	def test_pending_receiver_cannot_confirm_collection(self):
		food_request = self.create_accepted_request()
		VolunteerAssignment.objects.create(request=food_request, volunteer=self.volunteer, status='DELIVERED')
		record = CollectionRecord.objects.create(request=food_request)
		self.receiver.profile.verification_status = 'PENDING'
		self.receiver.profile.save(update_fields=['verification_status'])
		self.client.force_login(self.receiver)
		self.client.post(reverse('confirm_collection', args=[food_request.pk]))
		record.refresh_from_db()
		self.assertFalse(record.receiver_confirmed)

	def test_profile_change_returns_approved_account_to_pending(self):
		self.client.force_login(self.donor)
		response = self.client.post(reverse('profile'), {
			'first_name': 'First',
			'last_name': 'Donor',
			'email': 'donor@example.com',
			'organization_type': 'INDIVIDUAL',
			'organization_name': '',
			'phone': '555-0199',
			'address': '45 Oak Avenue',
			'city': 'Springfield',
		})
		self.assertEqual(response.status_code, 302)
		self.donor.profile.refresh_from_db()
		self.assertEqual(self.donor.profile.verification_status, 'PENDING')

	def test_completion_waits_for_all_accepted_reservations(self):
		second_receiver = self.create_user('second-receiver', 'RECEIVER')
		first_request = self.create_accepted_request(self.receiver, servings=1)
		second_request = self.create_accepted_request(second_receiver, servings=1)
		for food_request in [first_request, second_request]:
			VolunteerAssignment.objects.create(request=food_request, volunteer=self.volunteer, status='DELIVERED')
			CollectionRecord.objects.create(request=food_request)

		self.confirm_handoff_as_both_parties(first_request)
		first_request.refresh_from_db()
		self.donation.refresh_from_db()
		self.assertEqual(first_request.status, 'COMPLETED')
		self.assertEqual(self.donation.status, 'FULL')

		self.confirm_handoff_as_both_parties(second_request)
		self.donation.refresh_from_db()
		self.assertEqual(self.donation.status, 'COLLECTED')

	def test_closing_listing_preserves_accepted_delivery(self):
		food_request = self.create_accepted_request()
		pending_request = DonationRequest.objects.create(donation=self.donation, receiver=self.create_user('pending-close', 'RECEIVER'), requested_servings=1)
		self.donation.refresh_from_db()
		self.donation.reserved_servings += 1
		self.donation.status = 'FULL'
		self.donation.save(update_fields=['reserved_servings', 'status'])
		self.client.force_login(self.donor)
		self.client.post(reverse('donation_cancel', args=[self.donation.pk]))
		food_request.refresh_from_db()
		pending_request.refresh_from_db()
		self.donation.refresh_from_db()
		self.assertEqual(food_request.status, 'ACCEPTED')
		self.assertEqual(pending_request.status, 'CANCELLED')
		self.assertEqual(self.donation.reserved_servings, 1)
		self.assertEqual(self.donation.status, 'CANCELLED')
		VolunteerAssignment.objects.create(request=food_request, volunteer=self.volunteer, status='DELIVERED')
		CollectionRecord.objects.create(request=food_request)
		self.confirm_handoff_as_both_parties(food_request)
		food_request.refresh_from_db()
		self.donation.refresh_from_db()
		self.assertEqual(food_request.status, 'COMPLETED')
		self.assertEqual(self.donation.status, 'CANCELLED')

	def test_completion_waits_while_pending_reservation_exists(self):
		accepted = self.create_accepted_request(servings=1)
		pending_receiver = self.create_user('pending-reservation', 'RECEIVER')
		pending = DonationRequest.objects.create(donation=self.donation, receiver=pending_receiver, requested_servings=1)
		self.donation.refresh_from_db()
		self.donation.reserved_servings += 1
		self.donation.status = 'FULL'
		self.donation.save(update_fields=['reserved_servings', 'status'])
		VolunteerAssignment.objects.create(request=accepted, volunteer=self.volunteer, status='DELIVERED')
		CollectionRecord.objects.create(request=accepted)
		self.confirm_handoff_as_both_parties(accepted)
		self.donation.refresh_from_db()
		self.assertEqual(accepted.__class__.objects.get(pk=accepted.pk).status, 'COMPLETED')
		self.assertEqual(self.donation.status, 'FULL')

		self.client.force_login(self.donor)
		self.client.post(reverse('request_decision', args=[pending.pk, 'reject']))
		self.donation.refresh_from_db()
		self.assertEqual(self.donation.status, 'AVAILABLE')

	def test_expiry_command_cancels_pending_and_preserves_completed_record(self):
		self.donation.total_servings = 3
		self.donation.reserved_servings = 2
		self.donation.pickup_deadline = timezone.now() - timedelta(minutes=5)
		self.donation.status = 'AVAILABLE'
		self.donation.save()
		pending = DonationRequest.objects.create(donation=self.donation, receiver=self.receiver, requested_servings=1)
		completed = DonationRequest.objects.create(donation=self.donation, receiver=self.create_user('done-receiver', 'RECEIVER'), requested_servings=1, status='COMPLETED')
		record = CollectionRecord.objects.create(request=completed, donor_confirmed=True, receiver_confirmed=True)
		call_command('expire_donations', stdout=StringIO())
		self.donation.refresh_from_db()
		pending.refresh_from_db()
		record.refresh_from_db()
		self.assertEqual(self.donation.status, 'EXPIRED')
		self.assertEqual(self.donation.reserved_servings, 1)
		self.assertEqual(pending.status, 'CANCELLED')
		self.assertTrue(record.donor_confirmed)
		self.assertTrue(record.receiver_confirmed)
		self.client.force_login(self.create_user('new-receiver', 'RECEIVER'))
		self.client.post(reverse('request_create', args=[self.donation.pk]), {'requested_servings': 1})
		self.assertFalse(DonationRequest.objects.filter(donation=self.donation, status='PENDING').exists())

	def test_rejection_releases_reserved_servings(self):
		response = self.request_all_servings()
		self.assertEqual(response.status_code, 302)
		self.donation.refresh_from_db()
		self.assertEqual(self.donation.reserved_servings, 2)
		self.assertEqual(self.donation.status, 'FULL')

		food_request = DonationRequest.objects.get(donation=self.donation)
		self.client.force_login(self.donor)
		response = self.client.post(reverse('request_decision', args=[food_request.pk, 'reject']))
		self.assertEqual(response.status_code, 302)
		self.donation.refresh_from_db()
		food_request.refresh_from_db()
		self.assertEqual(food_request.status, 'REJECTED')
		self.assertEqual(self.donation.reserved_servings, 0)
		self.assertEqual(self.donation.status, 'AVAILABLE')

	def test_delivery_completes_after_both_parties_confirm(self):
		self.request_all_servings()
		food_request = DonationRequest.objects.get(donation=self.donation)

		self.client.force_login(self.donor)
		self.client.post(reverse('request_decision', args=[food_request.pk, 'accept']))
		self.client.force_login(self.volunteer)
		self.client.post(reverse('claim_delivery', args=[food_request.pk]))
		assignment = VolunteerAssignment.objects.get(request=food_request)
		self.client.post(reverse('update_delivery', args=[assignment.pk, 'PICKED_UP']))
		self.client.post(reverse('update_delivery', args=[assignment.pk, 'DELIVERED']))

		self.client.force_login(self.receiver)
		self.client.post(reverse('confirm_collection', args=[food_request.pk]))
		food_request.refresh_from_db()
		self.assertEqual(food_request.status, 'ACCEPTED')
		record = CollectionRecord.objects.get(request=food_request)
		self.assertTrue(record.receiver_confirmed)
		self.assertFalse(record.donor_confirmed)

		self.client.force_login(self.donor)
		self.client.post(reverse('confirm_collection', args=[food_request.pk]))
		food_request.refresh_from_db()
		self.donation.refresh_from_db()
		record.refresh_from_db()
		self.assertEqual(food_request.status, 'COMPLETED')
		self.assertEqual(self.donation.status, 'COLLECTED')
		self.assertTrue(record.receiver_confirmed)
		self.assertTrue(record.donor_confirmed)

	def test_homepage_and_donation_search_render(self):
		response = self.client.get(reverse('home'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Rescue Food.')
		self.assertContains(response, 'Share Hope.')
		self.assertContains(response, 'Reduce Waste.')
		self.assertContains(response, 'How It Works')
		self.assertContains(response, 'Restaurants &amp; hotels')
		self.assertContains(response, reverse('donation_create'))
		self.assertContains(response, reverse('donation_list'))
		self.assertEqual(response.context['stats']['listing_count'], 1)
		self.assertEqual(response.context['stats']['servings'], 2)
		response = self.client.get(reverse('donation_list'), {'city': 'Springfield'})
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Community lunch')

	def test_find_food_filters_by_name_category_city_and_food_type(self):
		category, _ = FoodCategory.objects.get_or_create(category_name='Prepared meals')
		self.donation.category = category
		self.donation.save(update_fields=['category'])
		response = self.client.get(reverse('donation_list'), {
			'q': 'Community lunch',
			'category': str(category.pk),
			'city': 'Springfield',
			'food_type': 'VEG',
			'sort': 'newest',
		})
		self.assertEqual(response.status_code, 200)
		self.assertEqual(list(response.context['donations']), [self.donation])
		self.assertContains(response, 'Prepared meals')
		self.assertContains(response, 'Vegetarian')

	def test_find_food_shows_expired_listings_as_unavailable(self):
		now = timezone.now()
		base_data = {
			'donor': self.donor,
			'description': 'Fresh food offer',
			'food_type': 'VEG',
			'total_servings': 2,
			'prepared_at': now - timedelta(hours=1),
			'pickup_deadline': now + timedelta(hours=3),
			'pickup_address': 'Private address',
			'city': 'Springfield',
		}
		FoodDonation.objects.create(title='Fully reserved', reserved_servings=2, **base_data)
		FoodDonation.objects.create(title='Cancelled listing', status='CANCELLED', **base_data)
		FoodDonation.objects.create(title='Full status listing', status='FULL', **base_data)
		FoodDonation.objects.create(title='Expired deadline', pickup_deadline=now - timedelta(minutes=1), **{
			key: value for key, value in base_data.items() if key != 'pickup_deadline'
		})
		response = self.client.get(reverse('donation_list'))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context['page_obj'].paginator.count, 2)
		self.assertContains(response, 'Community lunch')
		self.assertContains(response, 'Expired deadline')
		self.assertContains(response, 'Expired — unavailable for pickup or new requests.')
		for unavailable_title in ['Fully reserved', 'Cancelled listing', 'Full status listing']:
			self.assertNotContains(response, unavailable_title)

	def test_expired_food_detail_does_not_allow_new_requests(self):
		self.donation.pickup_deadline = timezone.now() - timedelta(minutes=1)
		self.donation.save(update_fields=['pickup_deadline'])
		self.client.force_login(self.receiver)
		response = self.client.get(reverse('donation_detail', args=[self.donation.pk]))
		self.assertContains(response, 'Expired')
		self.assertContains(response, 'unavailable for new requests')
		self.assertNotContains(response, 'Request Food')

	def test_find_food_sorts_newest_first_and_preserves_filters_in_pagination(self):
		for index in range(9):
			FoodDonation.objects.create(
				donor=self.donor,
				title=f'Community extra meal {index}',
				description='Community food offer',
				food_type='VEG',
				total_servings=3,
				prepared_at=timezone.now() - timedelta(hours=1),
				pickup_deadline=timezone.now() + timedelta(days=1),
				pickup_address='Private address',
				city='Springfield',
			)
		response = self.client.get(reverse('donation_list'), {'q': 'Community', 'sort': 'newest'})
		self.assertEqual(response.context['page_obj'].paginator.count, 10)
		page_rows = list(response.context['donations'])
		self.assertEqual(page_rows, sorted(page_rows, key=lambda row: (row.created_at, row.pk), reverse=True))
		page_two = self.client.get(reverse('donation_list'), {'q': 'Community', 'sort': 'newest', 'page': 2})
		self.assertEqual(page_two.context['page_obj'].number, 2)
		self.assertContains(page_two, 'q=Community&amp;sort=newest&amp;page=1')

	def test_find_food_card_displays_donor_organization(self):
		self.donor.profile.organization_name = 'Springfield Community Kitchen'
		self.donor.profile.save(update_fields=['organization_name'])
		response = self.client.get(reverse('donation_list'))
		self.assertContains(response, 'Springfield Community Kitchen')

	def test_food_detail_request_action_requires_approved_receiver(self):
		self.client.force_login(self.receiver)
		response = self.client.get(reverse('donation_detail', args=[self.donation.pk]))
		self.assertContains(response, 'Request Food')
		self.assertNotContains(response, self.donation.pickup_address)
		self.receiver.profile.verification_status = 'PENDING'
		self.receiver.profile.save(update_fields=['verification_status'])
		response = self.client.get(reverse('donation_detail', args=[self.donation.pk]))
		self.assertNotContains(response, 'Request Food')
		self.assertContains(response, 'must be approved before requesting')

	def test_signup_creates_profile_and_starts_session(self):
		response = self.client.post(reverse('signup'), {
			'username': 'newdonor',
			'first_name': 'Jordan',
			'last_name': 'Lee',
			'email': 'jordan@example.com',
			'password1': 'NourishLoop!2026',
			'password2': 'NourishLoop!2026',
			'role': 'DONOR',
			'organization_type': 'RESTAURANT',
			'organization_name': 'Local Table',
			'phone': '555-0188',
			'address': '45 Oak Avenue',
			'city': 'Springfield',
		})
		self.assertEqual(response.status_code, 302)
		user = User.objects.get(username='newdonor')
		self.assertEqual(user.profile.role, 'DONOR')
		self.assertEqual(user.first_name, 'Jordan')
		self.assertTrue('_auth_user_id' in self.client.session)

	def test_registration_and_login_work_for_each_member_role(self):
		role_data = [
			('DONOR', 'RESTAURANT'),
			('RECEIVER', 'CHARITY'),
			('VOLUNTEER', 'INDIVIDUAL'),
		]
		for role, organization_type in role_data:
			with self.subTest(role=role):
				username = f'new-{role.lower()}'
				response = self.client.post(reverse('signup'), {
					'username': username,
					'first_name': 'New',
					'last_name': role.title(),
					'email': f'{username}@example.com',
					'password1': 'NourishLoop!2026',
					'password2': 'NourishLoop!2026',
					'role': role,
					'organization_type': organization_type,
					'organization_name': 'Community Partner',
					'phone': '555-0188',
					'address': '45 Oak Avenue',
					'city': 'Springfield',
				})
				self.assertRedirects(response, reverse('dashboard'))
				user = User.objects.get(username=username)
				self.assertEqual(user.profile.role, role)
				self.assertEqual(user.profile.verification_status, 'PENDING')
				self.client.post(reverse('logout'))
				login_response = self.client.post(reverse('login'), {
					'username': username,
					'password': 'NourishLoop!2026',
				}, follow=True)
				self.assertRedirects(login_response, reverse('dashboard'))
				self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)
				dashboard_action = {
					'DONOR': 'Share food',
					'RECEIVER': 'Find food',
					'VOLUNTEER': 'Delivery board',
				}[role]
				self.assertContains(login_response, dashboard_action)
				self.client.post(reverse('logout'))

	def test_signup_rejects_mismatched_password_confirmation(self):
		response = self.client.post(reverse('signup'), {
			'username': 'mismatch',
			'first_name': 'Mismatch',
			'last_name': 'Password',
			'email': 'mismatch@example.com',
			'password1': 'NourishLoop!2026',
			'password2': 'DifferentPassword!2026',
			'role': 'RECEIVER',
			'organization_type': 'NGO',
			'phone': '555-0123',
			'address': '45 Oak Avenue',
			'city': 'Springfield',
		})
		self.assertEqual(response.status_code, 200)
		self.assertFalse(User.objects.filter(username='mismatch').exists())
		self.assertContains(response, "The two password fields didn’t match")

	def test_password_reset_page_and_email_flow(self):
		from django.core import mail
		from django.test import override_settings

		self.receiver.email = 'reset@example.com'
		self.receiver.save(update_fields=['email'])
		response = self.client.get(reverse('password_reset'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'email')
		with override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
			response = self.client.post(reverse('password_reset'), {'email': 'reset@example.com'}, follow=True)
			self.assertEqual(response.status_code, 200)
			self.assertContains(response, 'Check your inbox')
			self.assertEqual(len(mail.outbox), 1)
			reset_url = next(line for line in mail.outbox[0].body.splitlines() if line.startswith('http'))
			from urllib.parse import urlparse
			reset_path = urlparse(reset_url).path
			confirm_response = self.client.get(reset_path, follow=True)
			self.assertEqual(confirm_response.status_code, 200)
			confirm_path = confirm_response.request['PATH_INFO']
			complete_response = self.client.post(confirm_path, {
				'new_password1': 'ResetNourishLoop!2026',
				'new_password2': 'ResetNourishLoop!2026',
			}, follow=True)
			self.assertContains(complete_response, 'password has been updated')
		self.receiver.refresh_from_db()
		self.assertTrue(self.receiver.check_password('ResetNourishLoop!2026'))

	def test_share_food_form_lists_default_categories(self):
		self.client.force_login(self.donor)
		response = self.client.get(reverse('donation_create'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Prepared meals')
		self.assertContains(response, 'Fresh produce')
		self.assertContains(response, 'Bakery and bread')

	def test_about_and_how_it_works_pages_render_with_shared_navigation(self):
		about_response = self.client.get(reverse('about'))
		self.assertEqual(about_response.status_code, 200)
		self.assertContains(about_response, 'food is too valuable to go to waste')
		self.assertContains(about_response, '03 / MISSION')
		self.assertContains(about_response, reverse('contact'))

		how_response = self.client.get(reverse('how_it_works'))
		self.assertEqual(how_response.status_code, 200)
		for role_label in ['FOR DONORS', 'FOR RECEIVERS', 'FOR VOLUNTEERS']:
			self.assertContains(how_response, role_label)
		self.assertContains(how_response, 'approved profile')

	def test_contact_page_renders_common_navigation_and_form(self):
		response = self.client.get(reverse('contact'))
		self.assertEqual(response.status_code, 200)
		for field_name in ['name', 'email', 'subject', 'message']:
			self.assertContains(response, f'name="{field_name}"')
		self.assertContains(response, reverse('about'))
		self.assertContains(response, reverse('how_it_works'))

	def test_contact_form_rejects_invalid_submission(self):
		response = self.client.post(reverse('contact'), {
			'name': 'Visitor',
			'email': 'not-an-email',
			'subject': 'Question',
			'message': 'Please contact me.',
		})
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Enter a valid email address')
		self.assertEqual(ContactEnquiry.objects.count(), 0)

	def test_valid_contact_submission_is_saved_and_shows_feedback(self):
		response = self.client.post(reverse('contact'), {
			'name': 'Community Kitchen',
			'email': 'hello@example.org',
			'subject': 'Partnering with NourishLoop',
			'message': 'We would like to coordinate local food pickups.',
		}, follow=True)
		self.assertEqual(response.redirect_chain, [(reverse('contact'), 302)])
		enquiry = ContactEnquiry.objects.get()
		self.assertEqual(enquiry.name, 'Community Kitchen')
		self.assertEqual(enquiry.email, 'hello@example.org')
		self.assertEqual(enquiry.subject, 'Partnering with NourishLoop')
		self.assertEqual(enquiry.message, 'We would like to coordinate local food pickups.')
		self.assertContains(response, 'Your message has been received')

	def test_logout_uses_branded_signed_out_page(self):
		self.client.force_login(self.donor)
		response = self.client.post(reverse('logout'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Thanks for being part of the loop.')
		self.assertContains(response, reverse('login'))
		self.assertNotIn('_auth_user_id', self.client.session)
