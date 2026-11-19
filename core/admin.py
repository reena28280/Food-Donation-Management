
from django.contrib import admin
from .models import ContactEnquiry, Notification

admin.site.register(Notification)


@admin.register(ContactEnquiry)
class ContactEnquiryAdmin(admin.ModelAdmin):
	list_display = ('name', 'email', 'subject', 'submitted_at')
	list_filter = ('submitted_at',)
	search_fields = ('name', 'email', 'subject', 'message')
	readonly_fields = ('name', 'email', 'subject', 'message', 'submitted_at')
