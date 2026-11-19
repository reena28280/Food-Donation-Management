
from django.db.models import Count, F, Sum
from django.shortcuts import get_object_or_404, render
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.utils import timezone
from accounts.models import Profile
from donations.models import FoodDonation
from foodrequests.models import DonationRequest
from .forms import ContactEnquiryForm
from .models import Notification

def home(request):
    available = FoodDonation.objects.filter(status='AVAILABLE', pickup_deadline__gt=timezone.now())
    stats = available.aggregate(
        listing_count=Count('id'),
        servings=Sum(F('total_servings') - F('reserved_servings')),
    )
    completed_servings = DonationRequest.objects.filter(status='COMPLETED').aggregate(
        total=Sum('requested_servings'),
    )['total'] or 0
    approved_partners = Profile.objects.filter(
        verification_status='APPROVED',
        role__in=['DONOR', 'RECEIVER'],
    ).count()
    donations = available.select_related('category').order_by('pickup_deadline')[:3]
    return render(request, 'core/landing.html', {
        'stats': stats,
        'completed_servings': completed_servings,
        'approved_partners': approved_partners,
        'recent_donations': donations,
        'user_role': Profile.objects.filter(user=request.user).values_list('role', flat=True).first() if request.user.is_authenticated and not request.user.is_staff else None,
    })


def about(request):
    return render(request, 'core/about.html')


def how_it_works(request):
    return render(request, 'core/how_it_works.html')


def contact(request):
    form = ContactEnquiryForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Thanks for contacting NourishLoop. Your message has been received.')
        return redirect('contact')
    return render(request, 'core/contact.html', {'form': form})


@login_required
def notification_list(request):
    if request.user.is_staff or request.user.is_superuser:
        return redirect('admin:index')
    notifications = Notification.objects.filter(user=request.user)
    return render(request, 'core/notifications.html', {
        'notifications': notifications,
        'unread_count': notifications.filter(is_read=False).count(),
    })


@login_required
def notification_mark_read(request, notification_id):
    if request.user.is_staff or request.user.is_superuser:
        return redirect('admin:index')
    if request.method == 'POST':
        notification = get_object_or_404(Notification, pk=notification_id, user=request.user)
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=['is_read'])
            messages.success(request, 'Notification marked as read.')
    return redirect('notification_list')
