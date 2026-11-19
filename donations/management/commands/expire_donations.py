from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Case, F, IntegerField, Sum, Value, When
from django.utils import timezone

from donations.models import FoodDonation


class Command(BaseCommand):
	help = 'Expire overdue available donations and release their pending reservations.'

	def handle(self, *args, **options):
		expired_count = 0
		now = timezone.now()
		ids = list(FoodDonation.objects.filter(
			status='AVAILABLE',
			pickup_deadline__lte=now,
		).values_list('pk', flat=True))

		for donation_id in ids:
			with transaction.atomic():
				donation = FoodDonation.objects.select_for_update().filter(
					pk=donation_id,
					status='AVAILABLE',
					pickup_deadline__lte=now,
				).first()
				if donation is None:
					continue

				pending = donation.requests.filter(status='PENDING')
				released_servings = pending.aggregate(total=Sum('requested_servings'))['total'] or 0
				pending.update(status='CANCELLED', updated_at=now)
				if released_servings:
					FoodDonation.objects.filter(pk=donation.pk).update(reserved_servings=Case(
						When(reserved_servings__gte=released_servings, then=F('reserved_servings') - released_servings),
						default=Value(0),
						output_field=IntegerField(),
					))
				donation.status = 'EXPIRED'
				donation.save(update_fields=['status'])
				expired_count += 1

		self.stdout.write(self.style.SUCCESS(f'Expired {expired_count} donation(s).'))