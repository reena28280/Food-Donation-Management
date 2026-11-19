from django.urls import path
from . import views

urlpatterns = [
    path('', views.donation_list, name='donation_list'),
    path('new/', views.donation_create, name='donation_create'),
    path('<int:pk>/', views.donation_detail, name='donation_detail'),
    path('<int:pk>/edit/', views.donation_edit, name='donation_edit'),
    path('<int:pk>/close/', views.donation_cancel, name='donation_cancel'),
]