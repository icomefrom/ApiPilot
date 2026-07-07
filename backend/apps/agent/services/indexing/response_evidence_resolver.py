"""响应证据解析器：优先复用历史响应，再按环境/方法策略决定是否试跑。"""
import logging

from apps.api_debug.models import ApiInterface, DebugResult

from .response_sampler import ResponseSampler

logger = logging.getLogger(__name__)

READ_METHODS = {'GET', 'HEAD', 'OPTIONS'}
WRITE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}


class ResponseEvidenceResolver:
    def __init__(self, sampler=None):
        self.sampler = sampler or ResponseSampler()

    def resolve(self, matches, *, project, environment=None, trial_policy=None):
        trial_policy = trial_policy or {}
        samples = {}
        statuses = []
        questions = []
        warnings = []

        for match in matches:
            step_index = match.get('step_index')
            selected = match.get('selected_interface') or {}
            interface_id = match.get('selected_interface_id') or selected.get('interface_id')
            if not interface_id:
                samples[step_index] = {'error': '未匹配接口，跳过响应证据获取', 'body_keys': []}
                statuses.append(self._status(step_index, None, 'blocked_no_interface'))
                continue

            interface = self._get_interface(interface_id, project)
            if not interface:
                samples[step_index] = {'error': f'接口 {interface_id} 不存在', 'body_keys': []}
                statuses.append(self._status(step_index, interface_id, 'blocked_interface_not_found'))
                continue

            history_sample = self._history_sample(interface)
            if history_sample:
                samples[step_index] = history_sample
                statuses.append(self._status(step_index, interface_id, 'ready_history', source='history'))
                continue

            decision = self._decide_trial(interface, environment, trial_policy, step_index)
            if decision == 'run':
                sample = self.sampler.sample_one(interface_id, env=environment)
                sample['evidence_source'] = 'trial_run'
                samples[step_index] = sample
                if sample.get('error'):
                    statuses.append(self._status(step_index, interface_id, 'failed_trial_run', source='trial_run', reason=sample.get('error')))
                    warnings.append(f'第 {step_index} 步试运行失败：{sample.get("error")}')
                else:
                    statuses.append(self._status(step_index, interface_id, 'ready_trial_run', source='trial_run'))
                continue

            reason = decision
            samples[step_index] = {'error': self._blocked_message(reason), 'body_keys': [], 'evidence_source': reason}
            statuses.append(self._status(step_index, interface_id, reason, reason=reason))
            if reason == 'blocked_need_write_authorization':
                questions.append(self._authorization_question(step_index, interface))
            elif reason == 'blocked_production_write':
                warnings.append(f'第 {step_index} 步「{interface.name}」是线上写接口，已跳过试运行')

        return {
            'response_samples': samples,
            'evidence_status': statuses,
            'questions': questions,
            'warnings': warnings,
        }

    def _get_interface(self, interface_id, project):
        try:
            return ApiInterface.objects.get(id=interface_id, project=project)
        except ApiInterface.DoesNotExist:
            return None

    def _history_sample(self, interface):
        row = (
            DebugResult.objects
            .filter(interface=interface, status=DebugResult.STATUS_SUCCESS)
            .exclude(response_body='')
            .order_by('-created_at')
            .first()
        )
        if not row:
            return None
        body_structure, body_keys = self.sampler._parse_response(row.response_body or '')
        return {
            'status_code': row.status_code,
            'body_structure': body_structure,
            'body_keys': body_keys,
            'error': None,
            'evidence_source': 'history',
            'collected_at': row.created_at.isoformat() if row.created_at else None,
        }

    def _decide_trial(self, interface, environment, trial_policy, step_index):
        method = (interface.method or 'GET').upper()
        if method in READ_METHODS:
            return 'run'
        if method in WRITE_METHODS:
            if self._is_production(environment):
                return 'blocked_production_write'
            if self._is_authorized(interface, trial_policy, step_index):
                return 'run'
            return 'blocked_need_write_authorization'
        return 'blocked_unknown_method'

    def _is_authorized(self, interface, trial_policy, step_index):
        step_ids = set(trial_policy.get('authorized_step_indexes') or [])
        interface_ids = set(trial_policy.get('authorized_interface_ids') or [])
        return step_index in step_ids or interface.id in interface_ids

    def _is_production(self, environment):
        if not environment:
            return False
        text = ' '.join([
            str(getattr(environment, 'name', '') or ''),
            str(getattr(environment, 'base_url', '') or ''),
            str(getattr(environment, 'ws_base_url', '') or ''),
            str(getattr(environment, 'rpc_base_url', '') or ''),
        ]).lower()
        prod_markers = ('生产', '线上', 'prod', 'production', 'live', 'online')
        return any(marker in text for marker in prod_markers)

    def _authorization_question(self, step_index, interface):
        return {
            'type': 'trial_run_authorization',
            'step_index': step_index,
            'interface_id': interface.id,
            'method': interface.method,
            'interface_name': interface.name,
            'url': interface.url,
            'message': f'第 {step_index} 步「{interface.name}」是写接口，当前环境需要授权试运行以获取响应字段',
        }

    def _blocked_message(self, reason):
        if reason == 'blocked_need_write_authorization':
            return '写接口需要用户授权后才会试运行'
        if reason == 'blocked_production_write':
            return '线上写接口不允许试运行'
        if reason == 'blocked_unknown_method':
            return '未知接口方法，跳过试运行'
        return '缺少响应证据'

    def _status(self, step_index, interface_id, status, source=None, reason=None):
        return {
            'step_index': step_index,
            'interface_id': interface_id,
            'status': status,
            'source': source,
            'reason': reason,
        }
