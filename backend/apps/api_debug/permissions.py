from rest_framework import permissions

from .models import Project, ProjectMember

ROLE_ORDER = {
    ProjectMember.ROLE_VIEWER: 10,
    ProjectMember.ROLE_EDITOR: 20,
    ProjectMember.ROLE_ADMIN: 30,
    ProjectMember.ROLE_OWNER: 40,
}
EDIT_ROLES = {ProjectMember.ROLE_OWNER, ProjectMember.ROLE_ADMIN, ProjectMember.ROLE_EDITOR}
MANAGE_ROLES = {ProjectMember.ROLE_OWNER, ProjectMember.ROLE_ADMIN}
OWNER_ROLES = {ProjectMember.ROLE_OWNER}


def get_membership(user, project):
    if not user or not user.is_authenticated or not project:
        return None
    if user.is_superuser:
        return ProjectMember(project=project, user=user, role=ProjectMember.ROLE_OWNER)
    try:
        return ProjectMember.objects.get(project=project, user=user)
    except ProjectMember.DoesNotExist:
        return None


def has_project_role(user, project, roles):
    membership = get_membership(user, project)
    return bool(membership and membership.role in roles)


def can_view(user, project):
    return get_membership(user, project) is not None


def can_edit(user, project):
    return has_project_role(user, project, EDIT_ROLES)


def can_manage(user, project):
    return has_project_role(user, project, MANAGE_ROLES)


def can_own(user, project):
    return has_project_role(user, project, OWNER_ROLES)


class ProjectResourcePermission(permissions.BasePermission):
    """Object-level permission for project-owned resources."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(view, 'action', None) in {'list', 'retrieve'}:
            return True
        if getattr(view, 'action', None) in {'create', 'execute', 'execute_adhoc', 'parse_curl', 'run_script', 'import_postman'}:
            project = getattr(view, 'get_current_project', lambda: None)()
            if getattr(view, 'action', None) in {'execute_adhoc', 'parse_curl', 'run_script'}:
                return project is None or can_view(request.user, project)
            return project is not None and can_edit(request.user, project)
        return True

    def has_object_permission(self, request, view, obj):
        project = getattr(obj, 'project', None)
        if project is None and hasattr(obj, 'chain'):
            project = getattr(obj.chain, 'project', None)
        if project is None and hasattr(obj, 'interface'):
            project = getattr(obj.interface, 'project', None)
        if request.method in permissions.SAFE_METHODS:
            return can_view(request.user, project)
        if getattr(view, 'action', None) in {'execute'}:
            return can_view(request.user, project)
        return can_edit(request.user, project)
