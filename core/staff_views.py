import csv
from collections import defaultdict

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import Profile
from donations.models import FoodDonation
from foodrequests.models import DonationRequest


User = get_user_model()
staff_required = user_passes_test(
	lambda user: user.is_authenticated and (user.is_staff or user.is_superuser),
	login_url='login',
)


def _dashboard_stats():
	return {
		'total_users': User.objects.filter(is_staff=False, is_superuser=False).count(),
		'donors': Profile.objects.filter(role='DONOR').count(),
		'receivers': Profile.objects.filter(role='RECEIVER').count(),
		'volunteers': Profile.objects.filter(role='VOLUNTEER').count(),
		'donations': FoodDonation.objects.count(),
		'requests': DonationRequest.objects.count(),
		'completed_collections': DonationRequest.objects.filter(status='COMPLETED').count(),
		'meals_donated': FoodDonation.objects.aggregate(total=Sum('total_servings'))['total'] or 0,
	}


def _monthly_activity():
	donations_by_month = FoodDonation.objects.annotate(month=TruncMonth('created_at')).values('month').annotate(
		donations=Count('id'),
		meals=Sum('total_servings'),
	).order_by('month')
	completed_by_month = DonationRequest.objects.filter(status='COMPLETED').annotate(
		month=TruncMonth('updated_at'),
	).values('month').annotate(
		collections=Count('id'),
		meals=Sum('requested_servings'),
	).order_by('month')
	activity = defaultdict(lambda: {'donations': 0, 'meals_donated': 0, 'completed_collections': 0, 'meals_collected': 0})
	for row in donations_by_month:
		key = row['month'].date()
		activity[key]['donations'] = row['donations']
		activity[key]['meals_donated'] = row['meals'] or 0
	for row in completed_by_month:
		key = row['month'].date()
		activity[key]['completed_collections'] = row['collections']
		activity[key]['meals_collected'] = row['meals'] or 0
	return [
		{'month': month, **activity[month]}
		for month in sorted(activity, reverse=True)[:12]
	]


@staff_required
def staff_dashboard(request):
	pending_profiles = Profile.objects.filter(
		role__in=['DONOR', 'RECEIVER'],
		verification_status='PENDING',
	).select_related('user').order_by('created_at')[:8]
	return render(request, 'core/staff_dashboard.html', {
		'stats': _dashboard_stats(),
		'pending_profiles': pending_profiles,
	})


@staff_required
def verification_queue(request):
	profiles = Profile.objects.filter(
		role__in=['DONOR', 'RECEIVER'],
		verification_status='PENDING',
	).select_related('user').order_by('created_at')
	return render(request, 'core/verification_queue.html', {'profiles': profiles})


@staff_required
def verify_profile(request, profile_id, decision):
	if request.method != 'POST' or decision not in ['approve', 'reject']:
		return redirect('staff_verification')
	profile = get_object_or_404(
		Profile,
		pk=profile_id,
		role__in=['DONOR', 'RECEIVER'],
		verification_status='PENDING',
	)
	profile.verification_status = 'APPROVED' if decision == 'approve' else 'REJECTED'
	profile.save(update_fields=['verification_status'])
	result = 'approved' if decision == 'approve' else 'rejected'
	messages.success(request, f'{profile.user.username} was {result}.')
	return redirect('staff_verification')


@staff_required
def staff_reports(request):
	return render(request, 'core/staff_reports.html', {
		'stats': _dashboard_stats(),
		'monthly_activity': _monthly_activity(),
	})


@staff_required
def staff_reports_csv(request):
	response = HttpResponse(content_type='text/csv; charset=utf-8')
	response['Content-Disposition'] = f'attachment; filename="nourishloop-report-{timezone.localdate():%Y-%m-%d}.csv"'
	writer = csv.writer(response)
	writer.writerow(['Report', 'Period', 'Metric', 'Value'])
	for metric, value in _dashboard_stats().items():
		writer.writerow(['Summary', 'All time', metric.replace('_', ' ').title(), value])
	for row in _monthly_activity():
		month = row['month'].strftime('%Y-%m')
		for metric in ['donations', 'meals_donated', 'completed_collections', 'meals_collected']:
			writer.writerow(['Monthly activity', month, metric.replace('_', ' ').title(), row[metric]])
	return response