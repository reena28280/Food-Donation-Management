
from django.db import models
from django.conf import settings


class Notification(models.Model):

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )

    message = models.TextField()

    is_read = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.message[:40]}"


class ContactEnquiry(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField(max_length=254)
    subject = models.CharField(max_length=200)
    message = models.TextField(max_length=5000)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f'{self.subject} — {self.name}'
