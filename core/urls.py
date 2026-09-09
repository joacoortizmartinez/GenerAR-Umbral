from django.urls import path

from . import views

urlpatterns = [
    path("healthz/", views.healthcheck, name="healthcheck"),
    path("meta/leadgen/", views.leadgen_webhook, name="leadgen-webhook"),
    path("meta/whatsapp/", views.whatsapp_webhook, name="whatsapp-webhook"),
]
