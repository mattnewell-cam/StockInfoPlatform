from django.urls import path
from . import views

app_name = 'companies'

urlpatterns = [
    path("notifications/", views.notification_list, name="notifications"),
    path("notifications/<int:notification_id>/read/", views.notification_mark_read, name="notification-mark-read"),
    path("<str:slug>/", views.CompanyDetailView.as_view(), name="company-detail"),
    path("<str:slug>/follow/", views.follow_company, name="follow-company"),
    path("<str:slug>/unfollow/", views.unfollow_company, name="unfollow-company"),
    path("<str:slug>/alerts/", views.alert_preferences, name="alert-preferences"),
    path("<str:slug>/prices/<str:period>/", views.intraday_prices, name="intraday-prices"),
    path("<str:slug>/notes/add/", views.add_note, name="add-note"),
    path("<str:slug>/news/", views.regulatory_newsfeed, name="regulatory-newsfeed"),
    path("<str:slug>/discussion/threads/", views.discussion_threads, name="discussion-threads"),
    path("<str:slug>/discussion/messages/", views.discussion_messages, name="discussion-messages"),
    path("<str:slug>/discussion/threads/<int:thread_id>/", views.discussion_thread_messages, name="discussion-thread-messages"),
    path("<str:slug>/discussion/threads/add/", views.add_thread, name="discussion-add-thread"),
    path("<str:slug>/discussion/threads/<int:thread_id>/messages/add/", views.add_message, name="discussion-add-message"),
    path("<str:slug>/chat/sessions/", views.chat_sessions, name="chat-sessions"),
    path("<str:slug>/chat/sessions/<int:session_id>/", views.chat_session_messages, name="chat-session-messages"),
    path("<str:slug>/chat/sessions/<int:session_id>/send/", views.chat_send_message, name="chat-send-message"),
    path("<str:slug>/chat/sessions/<int:session_id>/rename/", views.chat_session_rename, name="chat-session-rename"),
    path("<str:slug>/chat/sessions/<int:session_id>/delete/", views.chat_session_delete, name="chat-session-delete"),
]
