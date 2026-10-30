from django.urls import path
from . import views

app_name = 'subscriptions'

urlpatterns = [
    path('subscribe/', views.subscribe, name='subscribe'),
    path('confirm/<uuid:token>/', views.confirm, name='confirm'),
    path('success/', views.success, name='success'),
]
