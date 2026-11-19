
from django.urls import path
from . import views
from . import staff_views

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('how-it-works/', views.how_it_works, name='how_it_works'),
    path('contact/', views.contact, name='contact'),
    path('notifications/', views.notification_list, name='notification_list'),
    path('notifications/<int:notification_id>/read/', views.notification_mark_read, name='notification_mark_read'),
    path('staff/', staff_views.staff_dashboard, name='staff_dashboard'),
    path('staff/verification/', staff_views.verification_queue, name='staff_verification'),
    path('staff/verification/<int:profile_id>/<str:decision>/', staff_views.verify_profile, name='staff_verify_profile'),
    path('staff/reports/', staff_views.staff_reports, name='staff_reports'),
    path('staff/reports.csv', staff_views.staff_reports_csv, name='staff_reports_csv'),
]
