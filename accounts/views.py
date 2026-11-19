from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.utils.http import url_has_allowed_host_and_scheme
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from .forms import LoginForm, ProfileForm, SignUpForm
from .models import Profile
from donations.models import FoodDonation
from foodrequests.models import DonationRequest
from logistics.models import VolunteerAssignment


def signup(request):
	if request.user.is_authenticated:
		return redirect('dashboard')
	form = SignUpForm(request.POST or None)
	if request.method == 'POST' and form.is_valid():
		with transaction.atomic():
			user = form.save(commit=False)
			user.email = form.cleaned_data['email']
			user.first_name = form.cleaned_data['first_name']
			user.last_name = form.cleaned_data['last_name']
			user.save()
			Profile.objects.create(
				user=user,
				role=form.cleaned_data['role'],
				organization_type=form.cleaned_data['organization_type'],
				organization_name=form.cleaned_data['organization_name'],
				phone=form.cleaned_data['phone'],
				address=form.cleaned_data['address'],
				city=form.cleaned_data['city'],
			)
		login(request, user)
		messages.success(request, 'Your account is registered and is awaiting admin verification. You can browse food while we review your profile.')
		return redirect('dashboard')
	return render(request, 'accounts/signup.html', {'form': form})


@login_required
def profile(request):
	if request.user.is_staff or request.user.is_superuser:
		return redirect('admin:index')
	profile = Profile.objects.filter(user=request.user).first()
	is_profile_setup = profile is None
	if is_profile_setup:
		profile = Profile(user=request.user)
	verification_fields = ('organization_type', 'organization_name', 'phone', 'address', 'city')
	original_verification_values = {field: getattr(profile, field) for field in verification_fields}
	form = ProfileForm(request.POST or None, instance=profile, initial={
		'first_name': request.user.first_name,
		'last_name': request.user.last_name,
		'email': request.user.email,
	})
	if request.method == 'POST' and form.is_valid():
		if is_profile_setup:
			profile = form.save(commit=False)
			profile.user = request.user
			profile.verification_status = 'PENDING'
			profile.save()
		else:
			verification_changed = any(
				original_verification_values[field] != form.cleaned_data[field]
				for field in verification_fields
			)
			needs_reverification = profile.verification_status == 'APPROVED' and verification_changed
			form.save()
			if needs_reverification:
				profile.verification_status = 'PENDING'
				profile.save(update_fields=['verification_status'])
		request.user.first_name = form.cleaned_data['first_name']
		request.user.last_name = form.cleaned_data['last_name']
		request.user.email = form.cleaned_data['email']
		request.user.save(update_fields=['first_name', 'last_name', 'email'])
		if is_profile_setup:
			messages.success(request, 'Your NourishLoop profile has been created and is awaiting admin verification.')
			return redirect('dashboard')
		if verification_changed:
			messages.success(request, 'Your profile was updated and sent for verification again.')
		else:
			messages.success(request, 'Your profile has been updated.')
		return redirect('profile')
	return render(request, 'accounts/profile.html', {
		'form': form,
		'profile': profile,
		'is_profile_setup': is_profile_setup,
	})


@login_required
def dashboard(request):
	if request.user.is_staff or request.user.is_superuser:
		return redirect('admin:index')
	profile = Profile.objects.filter(user=request.user).first()
	if profile is None:
		messages.error(request, 'Complete your NourishLoop profile to continue.')
		return redirect('profile')
	if profile.verification_status == 'PENDING':
		messages.info(request, 'Your account is waiting for admin verification. You can browse food, but posting, requesting, and delivery actions remain locked until approval.')
	elif profile.verification_status == 'REJECTED':
		messages.error(request, 'Your account verification was not approved. Update your profile or contact an administrator for assistance.')
	context = {'profile': profile}
	if profile.role == 'DONOR':
		donations = FoodDonation.objects.filter(donor=request.user)
		requests = DonationRequest.objects.filter(donation__donor=request.user).select_related(
			'donation', 'receiver',
		).order_by('-created_at')
		context['stats'] = {
			'total_donations': donations.count(),
			'active_listings': donations.filter(status__in=['AVAILABLE', 'FULL'], pickup_deadline__gt=timezone.now()).count(),
			'requests': requests.count(),
			'completed': requests.filter(status='COMPLETED').count(),
		}
		context['received_requests'] = requests
	elif profile.role == 'RECEIVER':
		requests = DonationRequest.objects.filter(receiver=request.user).select_related(
			'donation', 'donation__donor',
		).order_by('-created_at')
		context['stats'] = {
			'requests': requests.count(),
			'pending': requests.filter(status='PENDING').count(),
			'accepted': requests.filter(status='ACCEPTED').count(),
			'rejected': requests.filter(status='REJECTED').count(),
			'completed': requests.filter(status='COMPLETED').count(),
		}
		context['my_food_requests'] = requests
	else:
		available_tasks = DonationRequest.objects.filter(status='ACCEPTED', volunteer_assignment__isnull=True).select_related(
			'donation', 'donation__donor', 'receiver',
		).order_by('donation__pickup_deadline')
		assignments = VolunteerAssignment.objects.filter(volunteer=request.user).select_related(
			'request__donation', 'request__receiver',
		).order_by('-assigned_at')
		completed_tasks = assignments.filter(status='DELIVERED', request__status='COMPLETED')
		open_assignments = assignments.exclude(status='CANCELLED').exclude(status='DELIVERED', request__status='COMPLETED')
		context.update({
			'stats': {
				'available': available_tasks.count(),
				'assigned': open_assignments.count(),
				'completed': completed_tasks.count(),
			},
			'available_tasks': available_tasks[:5],
			'assigned_tasks': open_assignments[:5],
			'completed_tasks': completed_tasks[:5],
		})
	return render(request, 'accounts/dashboard.html', context)


def login_view(request):
	from django.contrib.auth import login as auth_login

	if request.user.is_authenticated:
		return redirect('dashboard')
	form = LoginForm(request, data=request.POST or None)
	if request.method == 'POST' and form.is_valid():
		auth_login(request, form.get_user())
		next_url = request.POST.get('next') or request.GET.get('next')
		if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
			return redirect(next_url)
		if request.user.is_staff or request.user.is_superuser:
			return redirect('admin:index')
		profile = Profile.objects.filter(user=request.user).first()
		if profile and profile.verification_status == 'PENDING':
			messages.info(request, 'Your profile is pending admin verification. You can browse listings while restricted actions remain unavailable.')
		elif profile and profile.verification_status == 'REJECTED':
			messages.error(request, 'Your profile was not approved. Update your profile or contact an administrator.')
		return redirect('dashboard')
	return render(request, 'accounts/login.html', {'form': form})
