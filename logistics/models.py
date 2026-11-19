
from django.db import models
from django.conf import settings
from foodrequests.models import DonationRequest


class VolunteerAssignment(models.Model):

    STATUS_CHOICES = [
        ('ASSIGNED', 'Assigned'),
        ('PICKED_UP', 'Picked Up'),
        ('DELIVERED', 'Delivered'),
        ('CANCELLED', 'Cancelled'),
    ]

    request = models.OneToOneField(
        DonationRequest,
        on_delete=models.CASCADE,
        related_name='volunteer_assignment'
    )

    volunteer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='volunteer_assignments'
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='ASSIGNED'
    )

    assigned_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.volunteer.username} - {self.request}"


class CollectionRecord(models.Model):

    request = models.OneToOneField(
        DonationRequest,
        on_delete=models.CASCADE,
        related_name='collection_record'
    )

    collected_at = models.DateTimeField(
        null=True,
        blank=True
    )

    donor_confirmed = models.BooleanField(default=False)

    receiver_confirmed = models.BooleanField(default=False)

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Collection - Request {self.request.id}"
