
from django.contrib import admin
from .models import FoodCategory, FoodDonation


@admin.register(FoodCategory)
class FoodCategoryAdmin(admin.ModelAdmin):
    search_fields = ('category_name',)
    ordering = ('category_name',)


@admin.register(FoodDonation)
class FoodDonationAdmin(admin.ModelAdmin):
    list_display = ('title', 'donor', 'category', 'city', 'total_servings', 'reserved_servings', 'status', 'pickup_deadline')
    list_filter = ('status', 'food_type', 'category', 'city')
    search_fields = ('title', 'description', 'donor__username', 'donor__email', 'city')
    list_select_related = ('donor', 'category')
    date_hierarchy = 'created_at'
