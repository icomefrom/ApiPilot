import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { projectApi } from '../api/project'

export const useProjectStore = defineStore('project', () => {
  const projects = ref([])
  const activeProjectId = ref(null)
  const loading = ref(false)
  const members = ref([])
  const membersLoading = ref(false)

  const activeProject = computed(() => projects.value.find(p => p.id === activeProjectId.value) || null)
  const activeRole = computed(() => activeProject.value?.role || null)
  const canEdit = computed(() => ['owner', 'admin', 'editor'].includes(activeRole.value))
  const canManage = computed(() => ['owner', 'admin'].includes(activeRole.value))
  const canOwn = computed(() => activeRole.value === 'owner')

  async function fetchProjects() {
    loading.value = true
    try {
      const data = await projectApi.getProjects()
      projects.value = data.results || data
      restoreActiveProject()
      if (!activeProjectId.value && projects.value.length) {
        setActiveProject(projects.value[0].id)
      }
    } finally {
      loading.value = false
    }
  }

  function setActiveProject(id) {
    activeProjectId.value = id || null
    if (id) {
      localStorage.setItem('active_project_id', String(id))
    } else {
      localStorage.removeItem('active_project_id')
    }
  }

  function restoreActiveProject() {
    const savedId = parseInt(localStorage.getItem('active_project_id') || '', 10)
    if (savedId && projects.value.some(p => p.id === savedId)) {
      activeProjectId.value = savedId
    } else if (savedId) {
      localStorage.removeItem('active_project_id')
      activeProjectId.value = null
    }
  }

  async function createProject(data) {
    const project = await projectApi.createProject(data)
    await fetchProjects()
    setActiveProject(project.id)
    return project
  }

  async function fetchMembers(projectId = activeProjectId.value) {
    if (!projectId) {
      members.value = []
      return []
    }
    membersLoading.value = true
    try {
      const data = await projectApi.getMembers(projectId)
      members.value = data.results || data
      return members.value
    } finally {
      membersLoading.value = false
    }
  }

  async function inviteMember(projectId, data) {
    const member = await projectApi.inviteMember(projectId, data)
    await fetchMembers(projectId)
    await fetchProjects()
    return member
  }

  async function updateMemberRole(projectId, memberId, role) {
    const member = await projectApi.updateMemberRole(projectId, memberId, role)
    await fetchMembers(projectId)
    await fetchProjects()
    return member
  }

  async function removeMember(projectId, memberId) {
    await projectApi.removeMember(projectId, memberId)
    await fetchMembers(projectId)
    await fetchProjects()
  }

  async function deleteProject(id = activeProjectId.value) {
    if (!id) return
    await projectApi.deleteProject(id)
    if (activeProjectId.value === id) {
      setActiveProject(null)
    }
    await fetchProjects()
    if (!activeProjectId.value && projects.value.length) {
      setActiveProject(projects.value[0].id)
    }
  }

  return {
    projects,
    members,
    activeProjectId,
    activeProject,
    activeRole,
    canEdit,
    canManage,
    canOwn,
    loading,
    membersLoading,
    fetchProjects,
    setActiveProject,
    restoreActiveProject,
    createProject,
    fetchMembers,
    inviteMember,
    updateMemberRole,
    removeMember,
    deleteProject,
  }
})
