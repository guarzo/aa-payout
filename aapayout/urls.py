"""App URLs"""

# Django
from django.urls import path

# AA Payout
from aapayout import views

app_name: str = "aapayout"

urlpatterns = [
    path("", views.index, name="index"),
]
