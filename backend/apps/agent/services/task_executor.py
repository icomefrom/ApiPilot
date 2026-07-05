import logging
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime

from django.conf import settings
from django.db import connection

from apps.api_debug.models import Chain

from ..models import AgentTask
from .building.chain_draft_builder import ChainDraftBuilder
from .building.plan_validator import PlanValidator
from .indexing.candidate_preselector import CandidatePreselector
from .indexing.interface_indexer import InterfaceIndexer
from .indexing.response_sampler import ResponseSampler
from .llm.errors import LLMError
from .llm.gateway import LLMGateway
from .planning.dependency_planner import ModelDependencyPlanner
from .planning.interface_matcher import InterfaceMatcher
from .planning.step_planner import StepPlanner

logger = logging.getLogger(__name__)

AGENT_TASK_TIMEOUT = 300  # seconds, overall task timeout
MAX_CONCURRENT_TASKS = 3

_agent_semaphore = threading.Semaphore(MAX_CONCURRENT_TASKS)

# Progress mapping for each stage
STAGES = [
    {'key': 'step_planning', 'label': 'Step 1/3: 生成业务步骤', 'start': 5, 'end': 33},
    {'key': 'interface_matching', 'label': 'Step 2/3: 匹配接口候选', 'start': 38, 'end': 66},
    {'key': 'dependency_planning', 'label': 'Step 3/3: 规划参数依赖', 'start': 71, 'end': 95},
    {'key': 'draft_and_validate', 'label': '校验 & 生成草稿', 'start': 95, 'end': 100},
]


class AgentBusyError(Exception):
    """Too many concurrent agent tasks."""
    pass


def start_agent_plan_task(*, goal, project, user, auto_save=False, auto_execute=False, candidate_limit=5, environment_id=None):
    """Create an AgentTask and spawn a daemon thread to run orchestration.

    Returns the AgentTask instance (with task_id).
    Raises AgentBusyError if too many concurrent tasks.
    """
    if not _agent_semaphore.acquire(blocking=False):
        raise AgentBusyError('当前并发任务过多，请稍后重试')

    task = AgentTask.objects.create(
        task_type=AgentTask.TASK_TYPE_PLAN,
        input_data={
            'goal': goal,
            'project_id': project.id if project else None,
            'auto_save': auto_save,
            'auto_execute': auto_execute,
            'candidate_limit': candidate_limit,
            'environment_id': environment_id,
        },
        created_by=user,
        project=project,
    )

    thread = threading.Thread(
        target=_guarded_run,
        args=(str(task.task_id),),
        name=f'agent-task-{task.task_id}',
        daemon=True,
    )
    thread.start()

    return task


def _guarded_run(task_id_str):
    """Semaphore-guarded wrapper: always releases semaphore & closes DB connection."""
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_run_agent_task, task_id_str)
            try:
                future.result(timeout=AGENT_TASK_TIMEOUT)
            except FuturesTimeoutError:
                _mark_timeout(task_id_str)
    except Exception:
        logger.exception(f'AgentTask {task_id_str} unexpected error')
    finally:
        _agent_semaphore.release()
        connection.close()


def _run_agent_task(task_id_str):
    """Run the full orchestration pipeline, updating AgentTask as it progresses."""
    try:
        task = AgentTask.objects.get(task_id=task_id_str)
    except AgentTask.DoesNotExist:
        logger.error(f'AgentTask {task_id_str} not found')
        return

    # Mark as running
    task.status = AgentTask.STATUS_RUNNING
    task.started_at = datetime.now()
    task.progress = 0
    task.current_step = '初始化'
    task.save(update_fields=['status', 'started_at', 'progress', 'current_step'])

    input_data = task.input_data or {}
    goal = input_data.get('goal', '')
    auto_save = input_data.get('auto_save', False)
    auto_execute = input_data.get('auto_execute', False)
    candidate_limit = input_data.get('candidate_limit', 5)
    environment_id = input_data.get('environment_id')
    project = task.project

    # 加载环境配置
    environment = None
    if environment_id:
        try:
            from apps.api_debug.models import Environment
            environment = Environment.objects.get(id=environment_id, project=project)
            logger.info(f'[AgentTask] environment loaded: id={environment.id} name={environment.name} base_url={environment.base_url}')
        except Exception as e:
            logger.warning(f'[AgentTask] environment_id={environment_id} not found: {e}')
            environment = None
    else:
        logger.info('[AgentTask] no environment_id provided, dry-run without env')

    llm = LLMGateway()
    step_planner = StepPlanner(llm)
    indexer = InterfaceIndexer()
    preselector = CandidatePreselector()
    matcher = InterfaceMatcher(llm)
    sampler = ResponseSampler()
    dependency_planner = ModelDependencyPlanner(llm)
    builder = ChainDraftBuilder()
    validator = PlanValidator()

    # Shared context that accumulates across stages
    context = {
        'goal': goal,
        'steps': [],
        'step_plan': {},
        'profiles': [],
        'candidates_by_step': [],
        'matches': [],
        'dependency_plan': {},
        'chain_draft': {},
        'validation': {},
        'llm_trace': {},
    }

    try:
        # Stage 0: Initialize - build interface profiles (no LLM call)
        _update_progress(task, 3, '读取项目接口画像')
        profiles = indexer.build_profiles(project)
        context['profiles'] = profiles

        # Stage 1: Step planning
        _begin_stage(task, 'step_planning')
        step_plan, step_llm = step_planner.plan(goal)
        steps = step_plan.get('steps', [])
        context['steps'] = steps
        context['step_plan'] = step_plan
        context['llm_trace']['step_planning'] = step_llm
        _complete_stage(task, 'step_planning', step_plan)

        # Stage 1.5: Preselection (no LLM call)
        _update_progress(task, 36, '预选接口候选')
        candidates_by_step = preselector.select(steps, profiles, limit=candidate_limit)
        context['candidates_by_step'] = candidates_by_step

        # Stage 2: Interface matching
        _begin_stage(task, 'interface_matching')
        matches, match_llm = matcher.match(steps, candidates_by_step)
        context['matches'] = matches
        context['llm_trace']['interface_matching'] = match_llm
        _complete_stage(task, 'interface_matching', {
            'match_count': len([m for m in matches if m.get('selected_interface_id')]),
            'matches': matches,
        })

        # Stage 2.5: Response sampling (try-run, no LLM)
        _update_progress(task, 69, '试运行接口获取响应结构')
        response_samples = sampler.sample(matches, env=environment)
        context['response_samples'] = response_samples

        # Stage 3: Dependency planning
        _begin_stage(task, 'dependency_planning')
        dependency_plan, dependency_llm = dependency_planner.plan(steps, matches, response_samples=response_samples)
        context['dependency_plan'] = dependency_plan
        context['llm_trace']['dependency_planning'] = dependency_llm
        _complete_stage(task, 'dependency_planning', dependency_plan)

        # Stage 4: Build draft & validate (no LLM call)
        _update_progress(task, 95, '校验 & 生成草稿')
        chain_draft = builder.build(project, step_plan.get('goal') or goal, steps, matches, dependency_plan, response_samples=response_samples)
        context['chain_draft'] = chain_draft

        from apps.api_debug.permissions import can_edit
        validation = validator.validate(steps, matches, dependency_plan, chain_draft, auto_execute=auto_execute)
        context['validation'] = validation

        saved_chain = None
        if auto_save:
            if not can_edit(task.created_by, project):
                validation['valid'] = False
                validation.setdefault('missing_inputs', []).append({
                    'step': None,
                    'field': 'permission',
                    'message': '没有项目编辑权限，无法保存链路草稿',
                })
            else:
                saved_chain = Chain.objects.create(
                    project=project,
                    name=chain_draft['name'],
                    description=chain_draft['description'],
                    nodes=chain_draft['nodes'],
                    edges=chain_draft['edges'],
                    globals=chain_draft['globals'],
                    status=Chain.STATUS_DRAFT,
                    created_by=task.created_by,
                )

        # Build final result - same structure as the old sync response
        result = {
            'mode': 'model_driven',
            'llm_trace': context['llm_trace'],
            'step_plan': step_plan,
            'steps': steps,
            'candidates_by_step': candidates_by_step,
            'matches': matches,
            'dependency_plan': dependency_plan,
            'chain_draft': chain_draft,
            'validation': validation,
            'warnings': validation.get('warnings', []),
            'questions': step_plan.get('questions', []),
            'saved_chain_id': saved_chain.id if saved_chain else None,
            'project_id': project.id if project else None,
        }

        # Mark task completed
        task.status = AgentTask.STATUS_COMPLETED
        task.progress = 100
        task.current_step = '完成'
        task.result = result
        task.finished_at = datetime.now()
        task.save(update_fields=['status', 'progress', 'current_step', 'result', 'finished_at'])

    except LLMError as exc:
        _mark_failed(task, f'{exc.message}', llm_error=exc)
    except Exception as exc:
        logger.exception(f'AgentTask {task_id_str} failed')
        _mark_failed(task, f'{type(exc).__name__}: {str(exc)[:500]}')


def _begin_stage(task, stage_key):
    """Mark a stage as running in step_results and update progress."""
    stage = _get_stage(stage_key)
    if stage:
        task.current_step = stage['label']
        task.progress = stage['start']
    step_results = task.step_results or {}
    step_results[stage_key] = {'status': 'running'}
    task.step_results = step_results
    task.save(update_fields=['current_step', 'progress', 'step_results'])


def _complete_stage(task, stage_key, output=None):
    """Mark a stage as completed in step_results and update progress."""
    stage = _get_stage(stage_key)
    if stage:
        task.progress = stage['end']
    step_results = task.step_results or {}
    step_results[stage_key] = {'status': 'completed'}
    if output is not None:
        step_results[stage_key]['output'] = output
    task.step_results = step_results
    task.save(update_fields=['progress', 'step_results'])


def _update_progress(task, progress, current_step):
    """Update progress and current_step without changing step_results."""
    task.progress = progress
    task.current_step = current_step
    task.save(update_fields=['progress', 'current_step'])


def _get_stage(key):
    """Look up a stage by key."""
    for stage in STAGES:
        if stage['key'] == key:
            return stage
    return None


def _mark_failed(task, error_message, llm_error=None):
    """Mark task as failed with error details."""
    task.status = AgentTask.STATUS_FAILED
    task.error_message = error_message
    task.finished_at = datetime.now()

    # Mark the currently running stage as failed
    step_results = task.step_results or {}
    for key, value in step_results.items():
        if value.get('status') == 'running':
            step_results[key] = {
                'status': 'failed',
                'error': error_message[:500],
            }
    task.step_results = step_results

    # Store LLM error details in result if available
    if llm_error:
        task.result = {
            'success': False,
            'error_code': getattr(llm_error, 'error_code', 'LLM_ERROR'),
            'message': llm_error.message,
            'details': llm_error.details,
        }

    task.save(update_fields=['status', 'error_message', 'finished_at', 'step_results', 'result'])


def _mark_timeout(task_id_str):
    """Mark a task as timed out (called from the timeout wrapper)."""
    try:
        task = AgentTask.objects.get(task_id=task_id_str)
        task.status = AgentTask.STATUS_TIMEOUT
        task.error_message = f'任务超时（{AGENT_TASK_TIMEOUT}秒）'
        task.finished_at = datetime.now()
        task.save(update_fields=['status', 'error_message', 'finished_at'])
    except AgentTask.DoesNotExist:
        pass
