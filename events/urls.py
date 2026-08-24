from django.urls import path
from . import views
from .svg_view import serve_floor_plan

urlpatterns = [
    path('', views.home, name='home'),
    path('events/', views.event_list, name='event_list'),
    path('events/<int:event_id>/', views.event_detail, name='event_detail'),
    path('events/<int:event_id>/floor-plan/', views.floor_plan_view, name='floor_plan_view'),
    path('events/<int:event_id>/floor-plan/<int:section_id>/', views.floor_plan_view, name='floor_plan_section_view'),
    path('floor-plan.svg', serve_floor_plan, name='serve_floor_plan'),
    path('events/<int:event_id>/stall/<int:stall_id>/update/', views.stall_update, name='stall_update'),
    path('events/<int:event_id>/stall/create/', views.stall_create, name='stall_create'),
    path('reset/<int:event_id>/<str:token>/', views.remote_reset, name='remote_reset'),
    path('upload-images/<int:event_id>/<str:token>/', views.upload_images, name='upload_images'),
    path('seed-accessories/<str:token>/', views.seed_accessories, name='seed_accessories'),
]
