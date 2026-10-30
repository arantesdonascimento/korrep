"""
URL configuration for korrep project.
"""
from django.contrib import admin
from django.urls import path, include
from monitor.views import HomeView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', HomeView.as_view(), name='home'),
    path('subscriptions/', include('subscriptions.urls')),
]
