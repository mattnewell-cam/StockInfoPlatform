"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views

from companies.views import signup, verify_email, home, search_api, logout_view, robots_txt
from companies import views as company_views


urlpatterns = [
    path('robots.txt', robots_txt, name='robots_txt'),
    path('', home, name='home'),
    path('api/search/', search_api, name='search_api'),
    path('api/newsfeed/', company_views.newsfeed_api, name='newsfeed_api'),
    path('notes/', company_views.notes_home, name='notes_home'),
    path('notes/add-company/', company_views.notes_add_company, name='notes_add_company'),
    path('notes/<str:ticker>/', company_views.notes_company, name='notes_company'),
    path('screener/', company_views.screener_home, name='screener'),
    path('api/screener/run/', company_views.screener_run, name='screener_run'),
    path('api/screener/save/', company_views.screener_save, name='screener_save'),
    path('api/screener/saved/', company_views.screener_saved_list, name='screener_saved_list'),
    path('api/screener/saved/<int:screen_id>/delete/', company_views.screener_saved_delete, name='screener_saved_delete'),
    path('admin/', admin.site.urls),
    path('companies/', include(('companies.urls', 'companies'), namespace='companies')),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', logout_view, name='logout'),
    path('signup/', signup, name='signup'),
    path('verify/', verify_email, name='verify_email'),
]
