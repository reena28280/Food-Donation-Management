from django.contrib import messages
from django.db import transaction
from django.core.paginator import Paginator
from django.db.models import BooleanField, Case, CharField, F, IntegerField, OuterRef, Q, Subquery, Sum, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from accounts.models import Profile
from accounts.permissions import member_role_required
from .forms import FoodDonationForm
from .models import FoodCategory, FoodDonation


def donation_list(request):
    mine = request.GET.get('mine') == '1'
    selected_sort = 'newest'
    if mine:
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user.is_staff or request.user.is_superuser:
            return redirect('admin:index')
        profile = get_object_or_404(Profile, user=request.user)
        if profile.role != 'DONOR':
            messages.error(request, 'Only donor accounts can manage donation listings.')
            return redirect('dashboard')
        donations = FoodDonation.objects.select_related('category').filter(donor=request.user).order_by('-created_at')
    else:
        now = timezone.now()
        donations = FoodDonation.objects.select_related('donor', 'category').filter(
            status__in=['AVAILABLE', 'EXPIRED'],
            total_servings__gt=F('reserved_servings'),
        ).annotate(
            donor_organization=Subquery(
                Profile.objects.filter(user_id=OuterRef('donor_id')).values('organization_name')[:1],
                output_field=CharField(),
            ),
            is_expired=Case(
                When(status='EXPIRED', then=Value(True)),
                When(pickup_deadline__lte=now, then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            ),
        )
        city = request.GET.get('city', '').strip()
        food_type = request.GET.get('food_type', '').strip()
        query = request.GET.get('q', '').strip()
        category_id = request.GET.get('category', '').strip()
        sort = request.GET.get('sort', 'newest').strip()
        if city:
            donations = donations.filter(city__icontains=city)
        if food_type:
            if food_type in dict(FoodDonation.FOOD_TYPE_CHOICES):
                donations = donations.filter(food_type=food_type)
        if query:
            donations = donations.filter(Q(title__icontains=query) | Q(description__icontains=query) | Q(category__category_name__icontains=query))
        if category_id.isdigit():
            donations = donations.filter(category_id=int(category_id))
        sort_options = {
            'newest': '-created_at',
            'pickup': 'pickup_deadline',
        }
        if sort not in sort_options:
            sort = 'newest'
        selected_sort = sort
        donations = donations.order_by(sort_options[sort], '-pk')

    paginator = Paginator(donations, 9)
    page_obj = paginator.get_page(request.GET.get('page'))
    query_params = request.GET.copy()
    query_params.pop('page', None)
    return render(request, 'donations/list.html', {
        'donations': page_obj.object_list,
        'page_obj': page_obj,
        'query_params': query_params.urlencode(),
        'food_types': FoodDonation.FOOD_TYPE_CHOICES,
        'categories': FoodCategory.objects.order_by('category_name'),
        'selected_category': request.GET.get('category', ''),
        'selected_sort': selected_sort,
        'mine': mine,
        'user_profile': Profile.objects.filter(user=request.user).first() if request.user.is_authenticated and not request.user.is_staff else None,
    })


def donation_detail(request, pk):
    donation = get_object_or_404(FoodDonation.objects.select_related('donor', 'category'), pk=pk)
    is_expired = donation.status == 'EXPIRED' or donation.pickup_deadline <= timezone.now()
    is_member = request.user.is_authenticated and not request.user.is_staff and not request.user.is_superuser
    is_donor = is_member and donation.donor_id == request.user.id
    profile = Profile.objects.filter(user=request.user).first() if is_member else None
    can_manage = is_donor and profile and profile.role == 'DONOR' and profile.verification_status == 'APPROVED'
    has_open_requests = donation.requests.filter(status__in=['PENDING', 'ACCEPTED']).exists()
    can_edit = bool(
        can_manage
        and donation.status == 'AVAILABLE'
        and donation.reserved_servings == 0
        and not has_open_requests
    )
    is_accepted_receiver = is_member and profile and profile.role == 'RECEIVER' and donation.requests.filter(
        receiver=request.user, status__in=['ACCEPTED', 'COMPLETED'],
    ).exists()
    is_assigned_volunteer = is_member and profile and profile.role == 'VOLUNTEER' and donation.requests.filter(
        volunteer_assignment__volunteer=request.user,
        volunteer_assignment__status__in=['ASSIGNED', 'PICKED_UP', 'DELIVERED'],
    ).exists()
    requests = donation.requests.select_related('receiver', 'receiver__profile').order_by('-created_at') if is_donor else []
    user_request = None
    if is_member and not is_donor:
        user_request = donation.requests.filter(receiver=request.user).exclude(status__in=['REJECTED', 'CANCELLED']).first()
    return render(request, 'donations/detail.html', {
        'donation': donation,
        'is_expired': is_expired,
        'requests': requests,
        'is_donor': is_donor,
        'can_manage': can_manage,
        'can_edit': can_edit,
        'user_role': profile.role if profile else None,
        'user_approved': bool(profile and profile.verification_status == 'APPROVED'),
        'show_pickup_address': bool(is_donor or is_accepted_receiver or is_assigned_volunteer),
        'user_request': user_request,
    })


@member_role_required('DONOR', approved=True)
def donation_create(request):
    profile = get_object_or_404(Profile, user=request.user)
    if profile.role != 'DONOR':
        messages.error(request, 'A donor account is needed to post food.')
        return redirect('dashboard')
    form = FoodDonationForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        donation = form.save(commit=False)
        donation.donor = request.user
        donation.save()
        messages.success(request, 'Your food listing is live.')
        return redirect('donation_detail', pk=donation.pk)
    return render(request, 'donations/form.html', {'form': form, 'heading': 'Share surplus food'})


@member_role_required('DONOR', approved=True)
def donation_edit(request, pk):
    donation = get_object_or_404(FoodDonation, pk=pk, donor=request.user)
    if donation.reserved_servings or donation.requests.filter(status__in=['PENDING', 'ACCEPTED']).exists() or donation.status != 'AVAILABLE':
        messages.error(request, 'This listing can no longer be edited because it is reserved or closed.')
        return redirect('donation_detail', pk=pk)
    if request.method == 'POST':
        with transaction.atomic():
            donation = get_object_or_404(FoodDonation.objects.select_for_update(), pk=pk, donor=request.user)
            has_open_requests = donation.requests.filter(status__in=['PENDING', 'ACCEPTED']).exists()
            if donation.reserved_servings or has_open_requests or donation.status != 'AVAILABLE':
                messages.error(request, 'This listing can no longer be edited because it is reserved or closed.')
                return redirect('donation_detail', pk=pk)
            form = FoodDonationForm(request.POST, request.FILES, instance=donation)
            if form.is_valid():
                form.save()
                messages.success(request, 'Your listing has been updated.')
                return redirect('donation_detail', pk=pk)
    else:
        form = FoodDonationForm(instance=donation)
    return render(request, 'donations/form.html', {'form': form, 'heading': 'Edit food listing', 'donation': donation})


@member_role_required('DONOR', approved=True)
def donation_cancel(request, pk):
    donation = get_object_or_404(FoodDonation, pk=pk, donor=request.user)
    if request.method == 'POST':
        with transaction.atomic():
            donation = FoodDonation.objects.select_for_update().get(pk=pk)
            if donation.status not in ['COLLECTED', 'CANCELLED']:
                pending = donation.requests.filter(status='PENDING')
                released_servings = pending.aggregate(total=Sum('requested_servings'))['total'] or 0
                pending.update(status='CANCELLED', updated_at=timezone.now())
                if released_servings:
                    FoodDonation.objects.filter(pk=donation.pk).update(reserved_servings=Case(
                        When(reserved_servings__gte=released_servings, then=F('reserved_servings') - released_servings),
                        default=Value(0),
                        output_field=IntegerField(),
                    ))
                donation.status = 'CANCELLED'
                donation.save(update_fields=['status'])
                messages.success(request, 'The listing is closed. Accepted pickups remain active and can still be completed.')
    return redirect('donation_detail', pk=pk)
