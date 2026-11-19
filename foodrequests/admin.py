
from django.contrib import admin
from .models import DonationRequest


@admin.register(DonationRequest)
class DonationRequestAdmin(admin.ModelAdmin):
    list_display = ('donation', 'receiver', 'requested_servings', 'status', 'created_at', 'updated_at')
    list_filter = ('status', 'created_at', 'updated_at')
    search_fields = ('donation__title', 'receiver__username', 'receiver__email')
    list_select_related = ('donation', 'receiver')
    date_hierarchy = 'created_at'
