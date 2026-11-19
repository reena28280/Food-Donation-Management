from django.contrib import messages
from django.db import transaction
from django.db.models import Case, F, IntegerField, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from accounts.models import Profile
from accounts.permissions import member_role_required
from core.notifications import notify_users
from donations.models import FoodDonation
from .models import DonationRequest


@member_role_required('RECEIVER', approved=True)
def request_create(request, donation_id):
	profile = get_object_or_404(Profile, user=request.user)
	if profile.role != 'RECEIVER':
		messages.error(request, 'Only receiver accounts can request food.')
		return redirect('donation_detail', pk=donation_id)
	if request.method != 'POST':
		return redirect('donation_detail', pk=donation_id)
	servings = request.POST.get('requested_servings', '')
	message = request.POST.get('message', '').strip()
	try:
		servings = int(servings)
	except (TypeError, ValueError):
		messages.error(request, 'Enter a valid number of servings.')
		return redirect('donation_detail', pk=donation_id)
	if servings < 1:
		messages.error(request, 'Request at least one serving.')
		return redirect('donation_detail', pk=donation_id)
	with transaction.atomic():
		donation = get_object_or_404(FoodDonation.objects.select_for_update(), pk=donation_id)
		active_request = donation.requests.filter(receiver=request.user, status__in=['PENDING', 'ACCEPTED']).exists()
		if donation.donor_id == request.user.id or donation.status != 'AVAILABLE' or donation.pickup_deadline <= timezone.now():
			messages.error(request, 'This donation is no longer available for requests.')
		elif active_request:
			messages.error(request, 'You already have an active request for this donation.')
		else:
			reserved = FoodDonation.objects.filter(
				pk=donation.pk,
				status='AVAILABLE',
				pickup_deadline__gt=timezone.now(),
				total_servings__gte=F('reserved_servings') + servings,
			).update(reserved_servings=F('reserved_servings') + servings)
			if not reserved:
				messages.error(request, f'Only {donation.remaining_servings} servings remain, or the listing is no longer available.')
			else:
				DonationRequest.objects.create(
					donation=donation,
					receiver=request.user,
					requested_servings=servings,
					message=message,
				)
				notify_users([donation.donor], f'{request.user.get_full_name() or request.user.username} requested {servings} servings of {donation.title}.')
				donation.refresh_from_db(fields=['reserved_servings', 'status'])
				if donation.remaining_servings == 0:
					donation.status = 'FULL'
					donation.save(update_fields=['status'])
				messages.success(request, 'Your food request has been sent to the donor.')
	return redirect('my_requests')


def my_requests(request):
	if not request.user.is_authenticated:
		return redirect('login')
	if request.user.is_staff or request.user.is_superuser:
		return redirect('admin:index')
	profile = get_object_or_404(Profile, user=request.user)
	if profile.role == 'RECEIVER':
		requests = DonationRequest.objects.filter(receiver=request.user).select_related('donation', 'donation__donor').order_by('-created_at')
		incoming = False
	elif profile.role == 'DONOR':
		requests = DonationRequest.objects.filter(donation__donor=request.user).select_related('donation', 'receiver').order_by('-created_at')
		incoming = True
	else:
		messages.error(request, 'Requests are available to donor and receiver accounts.')
		return redirect('dashboard')
	return render(request, 'foodrequests/list.html', {
		'requests': requests,
		'incoming': incoming,
		'user_city': profile.city,
		'can_confirm': profile.verification_status == 'APPROVED',
	})


@member_role_required('DONOR', approved=True)
def request_decision(request, request_id, decision):
	if request.method != 'POST' or decision not in ['accept', 'reject']:
		return redirect('my_requests')
	with transaction.atomic():
		request_ref = get_object_or_404(DonationRequest, pk=request_id, donation__donor=request.user)
		donation = get_object_or_404(FoodDonation.objects.select_for_update(), pk=request_ref.donation_id)
		food_request = get_object_or_404(DonationRequest.objects.select_for_update(), pk=request_id, donation__donor=request.user)
		if food_request.status != 'PENDING':
			messages.error(request, 'This request has already been reviewed.')
		elif decision == 'accept':
			if donation.status not in ['AVAILABLE', 'FULL'] or donation.pickup_deadline <= timezone.now():
				messages.error(request, 'This listing is closed or overdue, so the request cannot be accepted.')
			else:
				food_request.status = 'ACCEPTED'
				food_request.save(update_fields=['status', 'updated_at'])
				notify_users([food_request.receiver], f'Your request for {donation.title} was accepted by the donor.')
				messages.success(request, 'Request accepted. A volunteer can now claim the delivery.')
		else:
			food_request.status = 'REJECTED'
			food_request.save(update_fields=['status', 'updated_at'])
			notify_users([food_request.receiver], f'Your request for {donation.title} was declined. The servings are available again.')
			FoodDonation.objects.filter(pk=donation.pk).update(reserved_servings=Case(
				When(reserved_servings__gte=food_request.requested_servings, then=F('reserved_servings') - food_request.requested_servings),
				default=Value(0),
				output_field=IntegerField(),
			))
			donation.refresh_from_db()
			if donation.status == 'FULL' and donation.remaining_servings:
				donation.status = 'AVAILABLE'
				donation.save(update_fields=['status'])
			messages.success(request, 'Request declined and servings released.')
	if request.POST.get('return_to') == 'dashboard':
		return redirect('dashboard')
	return redirect('donation_detail', pk=food_request.donation_id)


@member_role_required('RECEIVER')
def request_cancel(request, request_id):
	if request.method == 'POST':
		with transaction.atomic():
			request_ref = get_object_or_404(DonationRequest, pk=request_id, receiver=request.user)
			donation = get_object_or_404(FoodDonation.objects.select_for_update(), pk=request_ref.donation_id)
			food_request = get_object_or_404(DonationRequest.objects.select_for_update(), pk=request_id, receiver=request.user)
			if food_request.status != 'PENDING':
				messages.error(request, 'Only pending requests can be cancelled.')
			else:
				food_request.status = 'CANCELLED'
				food_request.save(update_fields=['status', 'updated_at'])
				notify_users([donation.donor], f'{request.user.get_full_name() or request.user.username} cancelled their request for {donation.title}.')
				FoodDonation.objects.filter(pk=donation.pk).update(reserved_servings=Case(
					When(reserved_servings__gte=food_request.requested_servings, then=F('reserved_servings') - food_request.requested_servings),
					default=Value(0),
					output_field=IntegerField(),
				))
				donation.refresh_from_db()
				if donation.status == 'FULL' and donation.remaining_servings:
					donation.status = 'AVAILABLE'
					donation.save(update_fields=['status'])
				messages.success(request, 'Your request has been cancelled.')
	return redirect('my_requests')
