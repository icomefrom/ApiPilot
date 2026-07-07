from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.authentication.urls')),
    path('api/debug/', include('apps.api_debug.urls')),
    path('api/agent/', include('apps.agent.urls')),
]