from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'projects', views.ProjectViewSet, basename='project')
router.register(r'interfaces', views.ApiInterfaceViewSet, basename='api-interface')
router.register(r'groups', views.ApiGroupViewSet, basename='api-group')
router.register(r'results', views.DebugResultViewSet, basename='debug-result')
router.register(r'chains', views.ChainViewSet, basename='chain')
router.register(r'chain-results', views.ChainResultViewSet, basename='chain-result')
router.register(r'environments', views.EnvironmentViewSet, basename='environment')

urlpatterns = [
    path('test-post/', views.test_post, name='test-post'),
    path('test-rpc/', views.test_rpc, name='test-rpc'),
    path('', include(router.urls)),
]
