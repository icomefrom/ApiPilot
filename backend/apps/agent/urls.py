from django.urls import path

from .views import AgentPlanStatusView, AgentPlanView

urlpatterns = [
    path('plan/', AgentPlanView.as_view(), name='agent-plan'),
    path('plan/<uuid:task_id>/status/', AgentPlanStatusView.as_view(), name='agent-plan-status'),
]