from django.contrib import messages
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from accounts.models import Profile
from accounts.permissions import member_role_required
from core.notifications import notify_users
from donations.models import FoodDonation
from foodrequests.models import DonationRequest
from .models import CollectionRecord, VolunteerAssignment


@member_role_required('VOLUNTEER', approved=True)
def delivery_board(request):
	profile = get_object_or_404(Profile, user=request.user)
	if profile.role != 'VOLUNTEER':
		messages.error(request, 'The delivery board is for volunteer accounts.')
		return redirect('dashboard')
	available = DonationRequest.objects.filter(
		status='ACCEPTED', volunteer_assignment__isnull=True,
	).select_related('donation', 'donation__donor', 'receiver', 'receiver__profile').order_by('donation__pickup_deadline')
	assignments = VolunteerAssignment.objects.filter(volunteer=request.user).select_related(
		'request__donation', 'request__donation__donor', 'request__receiver', 'request__receiver__profile',
	).order_by('-assigned_at')
	return render(request, 'logistics/board.html', {
		'available': available,
		'assignments': assignments,
		'user_city': profile.city,
	})


@member_role_required('VOLUNTEER', approved=True)
def claim_delivery(request, request_id):
	if request.method == 'POST':
		with transaction.atomic():
			request_ref = get_object_or_404(DonationRequest, pk=request_id, status='ACCEPTED')
			FoodDonation.objects.select_for_update().get(pk=request_ref.donation_id)
			food_request = get_object_or_404(DonationRequest.objects.select_for_update(), pk=request_id, status='ACCEPTED')
			if hasattr(food_request, 'volunteer_assignment'):
				messages.error(request, 'Another volunteer has already claimed this delivery.')
			else:
				try:
					with transaction.atomic():
						VolunteerAssignment.objects.create(request=food_request, volunteer=request.user)
						CollectionRecord.objects.get_or_create(request=food_request)
						notify_users(
							[food_request.donation.donor, food_request.receiver, request.user],
							f'Delivery assigned for {food_request.donation.title}. The volunteer is {request.user.get_full_name() or request.user.username}.',
						)
					messages.success(request, 'Delivery claimed. The donor and receiver can now see your assignment.')
				except IntegrityError:
					messages.error(request, 'Another volunteer claimed this delivery first.')
	return redirect('delivery_board')


@member_role_required('VOLUNTEER', approved=True)
def update_delivery(request, assignment_id, status):
	if request.method == 'POST' and status in ['PICKED_UP', 'DELIVERED']:
		with transaction.atomic():
			assignment = get_object_or_404(VolunteerAssignment.objects.select_for_update(), pk=assignment_id, volunteer=request.user)
			allowed = {'ASSIGNED': 'PICKED_UP', 'PICKED_UP': 'DELIVERED'}
			if allowed.get(assignment.status) != status:
				messages.error(request, 'Delivery updates must follow the pickup sequence.')
			else:
				assignment.status = status
				assignment.save(update_fields=['status'])
				record, _ = CollectionRecord.objects.get_or_create(request=assignment.request)
				if status == 'PICKED_UP' and record.collected_at is None:
					record.collected_at = timezone.now()
					record.save(update_fields=['collected_at'])
				messages.success(request, 'Delivery status updated.')
	return redirect('delivery_board')


def confirm_collection(request, request_id):
	if not request.user.is_authenticated:
		return redirect('login')
	if request.user.is_staff or request.user.is_superuser:
		messages.error(request, 'Staff accounts cannot confirm member collections.')
		return redirect('admin:index')
	if request.method == 'POST':
		request_ref = get_object_or_404(DonationRequest.objects.only('donation_id'), pk=request_id)
		with transaction.atomic():
			donation = get_object_or_404(FoodDonation.objects.select_for_update(), pk=request_ref.donation_id)
			food_request = get_object_or_404(DonationRequest.objects.select_for_update(), pk=request_id)
			profile = Profile.objects.filter(user=request.user).first()
			is_donor = request.user.id == food_request.donation.donor_id and profile and profile.role == 'DONOR'
			is_receiver = request.user.id == food_request.receiver_id and profile and profile.role == 'RECEIVER'
			if not profile or profile.verification_status != 'APPROVED' or not (is_donor or is_receiver):
				messages.error(request, 'Only the donor or receiver can confirm this handoff.')
			elif food_request.status not in ['ACCEPTED', 'COMPLETED']:
				messages.error(request, 'Only an accepted delivery can be confirmed.')
			else:
				assignment = VolunteerAssignment.objects.select_for_update().filter(request=food_request).first()
				if assignment is None or assignment.status != 'DELIVERED':
					messages.error(request, 'The volunteer must mark this delivery as delivered first.')
				else:
					record, _ = CollectionRecord.objects.select_for_update().get_or_create(request=food_request)
					if is_receiver:
						record.receiver_confirmed = True
					else:
						record.donor_confirmed = True
					record.save(update_fields=['receiver_confirmed', 'donor_confirmed'])
					if record.receiver_confirmed and record.donor_confirmed:
						if food_request.status != 'COMPLETED':
							food_request.status = 'COMPLETED'
							food_request.save(update_fields=['status', 'updated_at'])
							volunteer = assignment.volunteer
							notify_users(
								[food_request.donation.donor, food_request.receiver, volunteer],
								f'The collection for {donation.title} is complete. Thank you for closing the food loop.',
							)
						still_reserved = donation.requests.filter(status__in=['PENDING', 'ACCEPTED']).exists()
						if donation.status not in ['CANCELLED', 'EXPIRED', 'COLLECTED'] and donation.remaining_servings == 0 and not still_reserved:
							donation.status = 'COLLECTED'
							donation.save(update_fields=['status'])
						messages.success(request, 'Handoff confirmed by both parties.')
					else:
						messages.success(request, 'Your confirmation is saved. The other party still needs to confirm.')
	return redirect('my_requests')
