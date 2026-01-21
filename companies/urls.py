from django.urls import path
from . import views

app_name = 'companies'

urlpatterns = [
    path("<str:ticker>/", views.CompanyDetailView.as_view(), name="company-detail"),
    path("<str:ticker>/prices/<str:period>/", views.intraday_prices, name="intraday-prices"),
    path("<str:ticker>/notes/add/", views.add_note, name="add-note"),
    path("<str:ticker>/news/", views.regulatory_newsfeed, name="regulatory-newsfeed"),
]
