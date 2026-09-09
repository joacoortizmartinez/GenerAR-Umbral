from django.contrib import admin
from django.urls import include, path

from core import views

urlpatterns = [
    path("", views.landing_page, name="landing"),
    path("admin/", admin.site.urls),
    path("webhooks/", include("core.urls")),
]
