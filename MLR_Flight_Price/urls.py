"""
Root URL Configuration — flight_price_predictor project.
"""

from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

urlpatterns = [
    # Admin panel (Jazzmin-powered)
    path("admin/", admin.site.urls),

    # Predictor app
    path("", include("predictor.urls", namespace="predictor")),

    # Convenience: bare root → home
    path("home/", lambda req: redirect("predictor:home"), name="home"),
]
