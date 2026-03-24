# config/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    # TODO Sprint 4: uncomment when dashboard views are built
    # path("", include("aqi_tracker.urls")),
]
