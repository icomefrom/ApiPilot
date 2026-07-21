import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api_debug', '0006_project_apigroup_project_apiinterface_project_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MockRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('enabled', models.BooleanField(default=True, verbose_name='启用')),
                ('status_code', models.IntegerField(default=200, verbose_name='响应状态码')),
                ('response_headers', models.JSONField(blank=True, default=dict, verbose_name='响应头')),
                ('response_body', models.TextField(blank=True, default='{}', verbose_name='响应体')),
                ('delay_ms', models.IntegerField(default=0, verbose_name='模拟延迟(ms)')),
                ('scenario', models.CharField(blank=True, default='default', max_length=50, verbose_name='场景标签')),
                ('content_type', models.CharField(blank=True, default='application/json', max_length=100, verbose_name='Content-Type')),
                ('response_mode', models.CharField(choices=[('static', '静态响应'), ('echo', '回显请求'), ('template', '模板响应')], default='static', max_length=20, verbose_name='响应模式')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('interface', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='mock_rule', to='api_debug.apiinterface', verbose_name='关联接口')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mock_rules', to=settings.AUTH_USER_MODEL, verbose_name='创建人')),
            ],
            options={
                'verbose_name': 'Mock 规则',
                'verbose_name_plural': 'Mock 规则',
                'db_table': 'api_debug_mock_rule',
                'ordering': ['-id'],
            },
        ),
    ]
