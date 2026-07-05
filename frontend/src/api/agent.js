import request from '../utils/request'

export const agentApi = {
  /** 提交编排任务（异步，立即返回 task_id） */
  submitPlan(data) {
    return request.post('/api/agent/plan/', data, { timeout: 10000 })
  },

  /** 轮询编排任务状态 */
  getPlanStatus(taskId) {
    return request.get(`/api/agent/plan/${taskId}/status/`, { timeout: 10000 })
  },
}