from django.urls import path
from . import views
from .svg_view import serve_floor_plan

urlpatterns = [
    path('', views.home, name='home'),
    path('events/', views.event_list, name='event_list'),
    path('events/<int:event_id>/', views.event_detail, name='event_detail'),
    path('events/<int:event_id>/floor-plan/', views.floor_plan_view, name='floor_plan_view'),
    path('floor-plan.svg', serve_floor_plan, name='serve_floor_plan'),
]
