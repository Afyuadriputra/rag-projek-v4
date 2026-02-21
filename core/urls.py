from django.urls import path
from . import views

urlpatterns = [
    # --- ROUTES UTAMA ---
    path('', views.chat_view, name='home'),
    
    # --- ROUTES AUTHENTICATION (BARU) ---
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # --- API ENDPOINTS ---
    path('api/upload/', views.upload_api, name='upload_api'),
    path('api/chat/', views.chat_api, name='chat_api'),
    path('api/documents/', views.documents_api, name='documents_api'),
    path('api/documents/<int:doc_id>/', views.document_detail_api, name='document_detail_api'),
    path('api/reingest/', views.reingest_api, name='reingest_api'),
    path('api/sessions/', views.sessions_api, name='sessions_api'),
    path('api/sessions/<int:session_id>/', views.session_detail_api, name='session_detail_api'),
    path('api/sessions/<int:session_id>/timeline/', views.session_timeline_api, name='session_timeline_api'),
    path('api/planner/start/', views.planner_start_v3_api, name='planner_start_v3_api'),
    path('api/planner/next-step/', views.planner_next_step_v3_api, name='planner_next_step_v3_api'),
    path('api/planner/execute/', views.planner_execute_v3_api, name='planner_execute_v3_api'),
    path('api/planner/cancel/', views.planner_cancel_v3_api, name='planner_cancel_v3_api'),


]
