from django.urls import path
from . import views

urlpatterns = [
    path('', views.delivery_board, name='delivery_board'),
    path('<int:request_id>/claim/', views.claim_delivery, name='claim_delivery'),
    path('<int:request_id>/confirm/', views.confirm_collection, name='confirm_collection'),
    path('<int:assignment_id>/<str:status>/', views.update_delivery, name='update_delivery'),
]