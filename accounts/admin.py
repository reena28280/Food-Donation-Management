
from django.contrib import admin
from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
	list_display = ('user', 'role', 'organization_type', 'organization_name', 'city', 'verification_status', 'created_at')
	list_filter = ('role', 'organization_type', 'verification_status', 'city')
	search_fields = ('user__username', 'user__email', 'organization_name', 'phone', 'city')
	list_editable = ('verification_status',)
	readonly_fields = ('created_at',)
