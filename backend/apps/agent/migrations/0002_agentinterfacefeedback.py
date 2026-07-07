# Generated manually for Agent interface feedback memory.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api_debug', '0006_project_apigroup_project_apiinterface_project_and_more'),
        ('agent', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AgentInterfaceFeedback',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('step_text', models.CharField(max_length=255, verbose_name='步骤文本')),
                ('normalized_step_text', models.CharField(db_index=True, max_length=255, verbose_name='归一化步骤文本')),
                ('reason', models.TextField(blank=True, default='', verbose_name='确认原因')),
                ('confirm_count', models.PositiveIntegerField(default=1, verbose_name='确认次数')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='agent_interface_feedbacks', to=settings.AUTH_USER_MODEL, verbose_name='创建人')),
                ('interface', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='agent_feedbacks', to='api_debug.apiinterface', verbose_name='接口')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='agent_interface_feedbacks', to='api_debug.project', verbose_name='项目')),
            ],
            options={
                'verbose_name': 'Agent接口匹配反馈',
                'verbose_name_plural': 'Agent接口匹配反馈',
                'db_table': 'api_debug_agent_interface_feedback',
                'unique_together': {('project', 'normalized_step_text', 'interface')},
                'indexes': [
                    models.Index(fields=['project', 'normalized_step_text'], name='api_debug_a_project_87a346_idx'),
                    models.Index(fields=['project', 'interface'], name='api_debug_a_project_b0f926_idx'),
                ],
            },
        ),
    ]
