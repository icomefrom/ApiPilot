from django.apps import AppConfig


class ApiDebugConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.api_debug'
    verbose_name = '接口测试'