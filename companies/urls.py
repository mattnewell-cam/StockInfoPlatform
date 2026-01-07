from django.urls import path
from . import views

app_name = 'companies'

urlpatterns = [
    path("<str:ticker>/", views.CompanyDetailView.as_view(), name="company-detail")
]