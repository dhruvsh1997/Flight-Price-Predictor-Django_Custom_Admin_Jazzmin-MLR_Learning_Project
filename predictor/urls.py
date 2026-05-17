"""predictor/urls.py"""

from django.urls import path
from . import views

app_name = "predictor"

urlpatterns = [
    path("",           views.home,       name="home"),
    path("predict/",   views.predict,    name="predict"),
    path("result/<int:pk>/", views.result, name="result"),
    path("dashboard/", views.dashboard,  name="dashboard"),
    path("api/options/", views.api_options, name="api_options"),
]
