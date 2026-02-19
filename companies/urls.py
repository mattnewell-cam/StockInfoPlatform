from django.urls import path
from . import views

app_name = 'companies'

urlpatterns = [
    path("notifications/", views.notification_list, name="notifications"),
    path("notifications/<int:notification_id>/read/", views.notification_mark_read, name="notification-mark-read"),
    path("<str:ticker>/", views.CompanyDetailView.as_view(), name="company-detail"),
    path("<str:ticker>/follow/", views.follow_company, name="follow-company"),
    path("<str:ticker>/unfollow/", views.unfollow_company, name="unfollow-company"),
    path("<str:ticker>/alerts/", views.alert_preferences, name="alert-preferences"),
    path("<str:ticker>/prices/<str:period>/", views.intraday_prices, name="intraday-prices"),
    path("<str:ticker>/notes/add/", views.add_note, name="add-note"),
    path("<str:ticker>/news/", views.regulatory_newsfeed, name="regulatory-newsfeed"),
    path("<str:ticker>/discussion/threads/", views.discussion_threads, name="discussion-threads"),
    path("<str:ticker>/discussion/messages/", views.discussion_messages, name="discussion-messages"),
    path("<str:ticker>/discussion/threads/<int:thread_id>/", views.discussion_thread_messages, name="discussion-thread-messages"),
    path("<str:ticker>/discussion/threads/add/", views.add_thread, name="discussion-add-thread"),
    path("<str:ticker>/discussion/threads/<int:thread_id>/messages/add/", views.add_message, name="discussion-add-message"),
    path("<str:ticker>/chat/sessions/", views.chat_sessions, name="chat-sessions"),
    path("<str:ticker>/chat/sessions/<int:session_id>/", views.chat_session_messages, name="chat-session-messages"),
    path("<str:ticker>/chat/sessions/<int:session_id>/send/", views.chat_send_message, name="chat-send-message"),
    path("<str:ticker>/chat/sessions/<int:session_id>/rename/", views.chat_session_rename, name="chat-session-rename"),
    path("<str:ticker>/chat/sessions/<int:session_id>/delete/", views.chat_session_delete, name="chat-session-delete"),
]
