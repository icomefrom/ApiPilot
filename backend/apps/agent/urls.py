from django.urls import path

from .views import (
    AgentInterfaceFeedbackView,
    AgentPlanCancelView,
    AgentPlanResumeView,
    AgentPlanStatusView,
    AgentPlanView,
)

urlpatterns = [
    path('plan/', AgentPlanView.as_view(), name='agent-plan'),
    path('plan/<uuid:task_id>/status/', AgentPlanStatusView.as_view(), name='agent-plan-status'),
    path('plan/<uuid:task_id>/cancel/', AgentPlanCancelView.as_view(), name='agent-plan-cancel'),
    path('plan/<uuid:task_id>/resume/', AgentPlanResumeView.as_view(), name='agent-plan-resume'),
    path('feedback/interface-match/', AgentInterfaceFeedbackView.as_view(), name='agent-interface-feedback'),
]
