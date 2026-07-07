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

  /** 取消编排任务 */
  cancelPlan(taskId) {
    return request.post(`/api/agent/plan/${taskId}/cancel/`, {}, { timeout: 10000 })
  },

  /** 从断点恢复编排任务（写接口授权后继续） */
  resumePlan(taskId, trialPolicy) {
    return request.post(`/api/agent/plan/${taskId}/resume/`, { trial_policy: trialPolicy }, { timeout: 10000 })
  },

  /** 记录用户确认的步骤-接口匹配反馈 */
  saveInterfaceFeedback(data) {
    return request.post('/api/agent/feedback/interface-match/', data, { timeout: 10000 })
  },
}
