
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


class Profile(models.Model):

    ORGANIZATION_TYPES_BY_ROLE = {
        'DONOR': {'COLLEGE', 'HOSTEL', 'RESTAURANT', 'HOTEL', 'EVENT', 'INDIVIDUAL', 'OTHER'},
        'RECEIVER': {
            'NGO', 'COMMUNITY', 'CHARITY', 'COMMUNITY_GROUP', 'ORPHANAGE',
            'OLD_AGE_HOME', 'COMMUNITY_CENTRE', 'INDIVIDUAL', 'OTHER',
        },
        'VOLUNTEER': {'COLLEGE', 'HOSTEL', 'NGO', 'COMMUNITY', 'INDIVIDUAL', 'OTHER'},
    }

    ROLE_CHOICES = [
        ('DONOR', 'Donor'),
        ('RECEIVER', 'Receiver'),
        ('VOLUNTEER', 'Volunteer'),
    ]

    ORGANIZATION_CHOICES = [
        ('COLLEGE', 'College'),
        ('HOSTEL', 'Hostel'),
        ('RESTAURANT', 'Restaurant'),
        ('HOTEL', 'Hotel'),
        ('NGO', 'NGO'),
        ('COMMUNITY', 'Community Kitchen'),
        ('EVENT', 'Event Organizer'),
        ('CHARITY', 'Charitable Organization'),
        ('COMMUNITY_GROUP', 'Community Group'),
        ('ORPHANAGE', 'Orphanage'),
        ('OLD_AGE_HOME', 'Old-age home'),
        ('COMMUNITY_CENTRE', 'Community centre'),
        ('INDIVIDUAL', 'Individual'),
        ('OTHER', 'Other'),
    ]

    VERIFICATION_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES
    )

    organization_type = models.CharField(
        max_length=20,
        choices=ORGANIZATION_CHOICES,
        default='INDIVIDUAL'
    )

    organization_name = models.CharField(
        max_length=150,
        blank=True
    )

    phone = models.CharField(max_length=15)

    address = models.TextField()

    city = models.CharField(max_length=100)

    verification_status = models.CharField(
        max_length=20,
        choices=VERIFICATION_CHOICES,
        default='PENDING'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        if self.role and self.organization_type not in self.ORGANIZATION_TYPES_BY_ROLE.get(self.role, set()):
            raise ValidationError({'organization_type': 'Choose an organization type that matches the account role.'})

    def __str__(self):
        return f"{self.user.username} - {self.role}"
