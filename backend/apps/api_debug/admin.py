from django.contrib import admin
from .models import ApiGroup, ApiInterface, DebugResult, Chain, ChainResult, Environment, Project, ProjectMember


class ProjectMemberInline(admin.TabularInline):
    model = ProjectMember
    extra = 0


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_by', 'created_at', 'updated_at']
    search_fields = ['name', 'description']
    inlines = [ProjectMemberInline]


@admin.register(ProjectMember)
class ProjectMemberAdmin(admin.ModelAdmin):
    list_display = ['project', 'user', 'role', 'joined_at']
    list_filter = ['role', 'joined_at']
    search_fields = ['project__name', 'user__username', 'user__email']


@admin.register(ApiGroup)
class ApiGroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'project', 'parent', 'sort_order', 'created_by', 'created_at']
    list_filter = ['project', 'created_at']
    search_fields = ['name']


@admin.register(ApiInterface)
class ApiInterfaceAdmin(admin.ModelAdmin):
    list_display = ['name', 'project', 'protocol', 'method', 'url', 'group', 'created_by', 'created_at']
    list_filter = ['project', 'protocol', 'method', 'created_at']
    search_fields = ['name', 'url']


@admin.register(Environment)
class EnvironmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'project', 'base_url', 'created_by', 'created_at']
    list_filter = ['project', 'created_at']
    search_fields = ['name', 'base_url']


@admin.register(Chain)
class ChainAdmin(admin.ModelAdmin):
    list_display = ['name', 'project', 'status', 'created_by', 'created_at']
    list_filter = ['project', 'status', 'created_at']
    search_fields = ['name']


@admin.register(ChainResult)
class ChainResultAdmin(admin.ModelAdmin):
    list_display = ['chain', 'project', 'status', 'started_at', 'finished_at', 'created_by']
    list_filter = ['project', 'status', 'started_at']


@admin.register(DebugResult)
class DebugResultAdmin(admin.ModelAdmin):
    list_display = ['interface', 'project', 'protocol', 'request_method', 'request_url',
                    'status_code', 'status', 'elapsed_ms', 'created_at']
    list_filter = ['project', 'protocol', 'status', 'created_at']
    search_fields = ['request_url']
