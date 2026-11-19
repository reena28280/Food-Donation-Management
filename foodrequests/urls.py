from django.urls import path
from . import views

urlpatterns = [
    path('', views.my_requests, name='my_requests'),
    path('<int:donation_id>/new/', views.request_create, name='request_create'),
    path('<int:request_id>/cancel/', views.request_cancel, name='request_cancel'),
    path('<int:request_id>/<str:decision>/', views.request_decision, name='request_decision'),
]