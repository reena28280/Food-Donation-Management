
from django.db import models
from django.conf import settings


class FoodCategory(models.Model):
    category_name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.category_name


class FoodDonation(models.Model):

    FOOD_TYPE_CHOICES = [
        ('VEG', 'Vegetarian'),
        ('NON_VEG', 'Non-Vegetarian'),
        ('VEGAN', 'Vegan'),
    ]

    STATUS_CHOICES = [
        ('AVAILABLE', 'Available'),
        ('FULL', 'Fully Reserved'),
        ('COLLECTED', 'Collected'),
        ('EXPIRED', 'Expired'),
        ('CANCELLED', 'Cancelled'),
    ]

    donor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='food_donations'
    )

    category = models.ForeignKey(
        FoodCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    title = models.CharField(max_length=200)

    description = models.TextField()

    food_type = models.CharField(
        max_length=10,
        choices=FOOD_TYPE_CHOICES,
        default='VEG'
    )

    total_servings = models.PositiveIntegerField()

    reserved_servings = models.PositiveIntegerField(default=0)

    image = models.ImageField(
        upload_to='food_images/',
        blank=True,
        null=True
    )

    prepared_at = models.DateTimeField()

    pickup_deadline = models.DateTimeField()

    pickup_address = models.TextField()

    city = models.CharField(max_length=100)

    allergens = models.TextField(
        blank=True,
        help_text='Mention allergens such as nuts, dairy, gluten, etc.'
    )

    storage_details = models.TextField(
        blank=True,
        help_text='Mention how the food has been stored.'
    )

    packaging_confirmed = models.BooleanField(default=False)

    storage_confirmed = models.BooleanField(default=False)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='AVAILABLE'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def remaining_servings(self):
        return max(0, self.total_servings - self.reserved_servings)

    def __str__(self):
        return self.title
