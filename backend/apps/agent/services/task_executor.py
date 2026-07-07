import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime

from django.conf import settings
from django.db import connection

from apps.api_debug.models import Chain

from ..models import AgentTask
from .building.chain_draft_builder import ChainDraftBuilder
from .building.plan_validator import PlanValidator
from .feedback_memory import load_feedback_memory
from .indexing.candidate_preselector import CandidatePreselector
from .indexing.project_index_cache import ProjectIndexCache
from .indexing.response_evidence_resolver import ResponseEvidenceResolver
from .indexing.response_sampler import ResponseSampler
from .llm.errors import LLMError
from .llm.gateway import LLMGateway
from .planning.dependency_planner import ModelDependencyPlanner
from .planning.assertion_planner import AssertionPlanner
from .planning.interface_matcher import InterfaceMatcher
from .planning.parameter_requirement_inferer import ParameterRequirementInferer
from .planning.step_planner import StepPlanner

logger = logging.getLogger(__name__)

AGENT_TASK_TIMEOUT = int(os.environ.get('AGENT_TASK_TIMEOUT', '600'))  # seconds, overall task timeout (cold start model loading can be slow)
MAX_CONCURRENT_TASKS = 3

_agent_semaphore = threading.Semaphore(MAX_CONCURRENT_TASKS)

# {task_id_str: threading.Event} — set() means cancel requested
_cancel_events: dict[str, threading.Event] = {}
_cancel_events_lock = threading.Lock()

# Progress mapping for each stage
STAGES = [
    {'key': 'step_planning', 'label': 'Step 1/4: 生成业务步骤', 'start': 5, 'end': 28},
    {'key': 'interface_matching', 'label': 'Step 2/4: 匹配接口候选', 'start': 33, 'end': 58},
    {'key': 'dependency_planning', 'label': 'Step 3/4: 规划参数依赖', 'start': 63, 'end': 82},
    {'key': 'assertion_planning', 'label': 'Step 4/4: 规划断言规则', 'start': 84, 'end': 94},
    {'key': 'draft_and_validate', 'label': '校验 & 生成草稿', 'start': 95, 'end': 100},
]


class AgentBusyError(Exception):
    """Too many concurrent agent tasks."""
    pass


class AgentCancelledError(Exception):
    """Task was cancelled by user."""
    pass


def start_agent_plan_task(*, goal, project, user, auto_save=False, auto_execute=False, candidate_limit=5, environment_id=None, trial_policy=None):
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
            'trial_policy': trial_policy or {},
        },
        created_by=user,
        project=project,
    )

    # Create cancel event
    cancel_event = threading.Event()
    with _cancel_events_lock:
        _cancel_events[str(task.task_id)] = cancel_event

    thread = threading.Thread(
        target=_guarded_run,
        args=(str(task.task_id), cancel_event),
        name=f'agent-task-{task.task_id}',
        daemon=True,
    )
    thread.start()

    return task


def resume_agent_plan_task(*, original_task, trial_policy, user=None):
    """Resume a completed agent task from its checkpoint, re-running only the
    stages that depend on the updated trial_policy.

    This avoids re-running LLM stages (step_planning, interface_matching,
    dependency_planning, assertion_planning) that don't depend on trial_policy.
    Instead, it restores their outputs from checkpoint and re-runs from
    Stage 2.5 (response_evidence) onwards.

    Returns a new AgentTask instance.
    Raises AgentBusyError if too many concurrent tasks.
    """
    if not _agent_semaphore.acquire(blocking=False):
        raise AgentBusyError('当前并发任务过多，请稍后重试')

    # Validate that original task has resumable checkpoint data
    step_results = original_task.step_results or {}
    required_stages = ['step_planning', 'interface_matching']
    for stage_key in required_stages:
        stage_data = step_results.get(stage_key, {})
        if stage_data.get('status') != 'completed' or 'output' not in stage_data:
            _agent_semaphore.release()
            raise ValueError(f'原始任务缺少 {stage_key} 阶段的断点数据，无法从断点恢复')

    # Merge trial_policy: new authorizations extend the original ones
    original_input = original_task.input_data or {}
    original_trial_policy = original_input.get('trial_policy') or {}
    merged_trial_policy = dict(original_trial_policy)
    # Extend authorized_step_indexes
    orig_steps = set(merged_trial_policy.get('authorized_step_indexes') or [])
    new_steps = set(trial_policy.get('authorized_step_indexes') or [])
    merged_trial_policy['authorized_step_indexes'] = list(orig_steps | new_steps)
    # Extend authorized_interface_ids
    orig_ifaces = set(merged_trial_policy.get('authorized_interface_ids') or [])
    new_ifaces = set(trial_policy.get('authorized_interface_ids') or [])
    merged_trial_policy['authorized_interface_ids'] = list(orig_ifaces | new_ifaces)

    # Create new task with reference to original task for resume
    task = AgentTask.objects.create(
        task_type=AgentTask.TASK_TYPE_PLAN,
        input_data={
            'goal': original_input.get('goal', ''),
            'project_id': original_input.get('project_id'),
            'auto_save': original_input.get('auto_save', False),
            'auto_execute': original_input.get('auto_execute', False),
            'candidate_limit': original_input.get('candidate_limit', 5),
            'environment_id': original_input.get('environment_id'),
            'trial_policy': merged_trial_policy,
            'resume_from_task_id': str(original_task.task_id),
        },
        created_by=user or original_task.created_by,
        project=original_task.project,
    )

    # Create cancel event
    cancel_event = threading.Event()
    with _cancel_events_lock:
        _cancel_events[str(task.task_id)] = cancel_event

    thread = threading.Thread(
        target=_guarded_resume_run,
        args=(str(task.task_id), cancel_event),
        name=f'agent-resume-{task.task_id}',
        daemon=True,
    )
    thread.start()

    return task


def cancel_agent_task(task_id_str):
    """Request cancellation of a running agent task.

    Returns True if cancel was requested, False if task not found or not running.
    """
    with _cancel_events_lock:
        event = _cancel_events.get(task_id_str)
    if event is None:
        return False
    event.set()
    logger.info(f'[AgentTask] 取消请求已发送: {task_id_str}')
    return True


def _guarded_run(task_id_str, cancel_event):
    """Semaphore-guarded wrapper: always releases semaphore & closes DB connection."""
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_run_agent_task, task_id_str, cancel_event)
            try:
                future.result(timeout=AGENT_TASK_TIMEOUT)
            except FuturesTimeoutError:
                _mark_timeout(task_id_str)
    except Exception:
        logger.exception(f'AgentTask {task_id_str} unexpected error')
    finally:
        _agent_semaphore.release()
        connection.close()
        with _cancel_events_lock:
            _cancel_events.pop(task_id_str, None)


def _guarded_resume_run(task_id_str, cancel_event):
    """Semaphore-guarded wrapper for resume tasks."""
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_run_agent_task_from_checkpoint, task_id_str, cancel_event)
            try:
                future.result(timeout=AGENT_TASK_TIMEOUT)
            except FuturesTimeoutError:
                _mark_timeout(task_id_str)
    except Exception:
        logger.exception(f'AgentTask (resume) {task_id_str} unexpected error')
    finally:
        _agent_semaphore.release()
        connection.close()
        with _cancel_events_lock:
            _cancel_events.pop(task_id_str, None)


def _check_cancelled(cancel_event, task=None):
    """Check if cancellation was requested. Raises AgentCancelledError if so.

    If task is provided, marks it as cancelled in DB.
    """
    if cancel_event.is_set():
        if task:
            task.refresh_from_db()
            if task.status in (AgentTask.STATUS_RUNNING, AgentTask.STATUS_PENDING):
                task.status = AgentTask.STATUS_CANCELLED
                task.current_step = '已取消'
                task.finished_at = datetime.now()
                task.save(update_fields=['status', 'current_step', 'finished_at'])
                # Mark running stage as cancelled
                step_results = task.step_results or {}
                for key, value in step_results.items():
                    if value.get('status') == 'running':
                        step_results[key] = {'status': 'cancelled'}
                task.step_results = step_results
                task.save(update_fields=['step_results'])
        raise AgentCancelledError('用户取消了任务')


def _run_agent_task(task_id_str, cancel_event):
    """Run the full orchestration pipeline, updating AgentTask as it progresses.

    Supports:
    - Cancellation via cancel_event
    - Stage checkpointing: each stage result is persisted to step_results,
      allowing resume or partial result retrieval on failure.
    - Project-level profile/embedding caching via ProjectIndexCache.
    """
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
    trial_policy = input_data.get('trial_policy') or {}
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
    matcher = InterfaceMatcher(llm)
    sampler = ResponseSampler()
    evidence_resolver = ResponseEvidenceResolver(sampler)
    dependency_planner = ModelDependencyPlanner(llm)
    parameter_inferer = ParameterRequirementInferer()
    assertion_planner = AssertionPlanner(llm)
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
        'parameter_requirements': [],
        'assertion_plan': [],
        'response_evidence': {},
        'chain_draft': {},
        'validation': {},
        'llm_trace': {},
    }

    try:
        # ---- Check cancel before starting ----
        _check_cancelled(cancel_event, task)

        # Stage 0: Initialize — build interface profiles (cached)
        _update_progress(task, 2, '读取项目接口画像')
        profiles, from_cache = ProjectIndexCache.get_profiles(project)
        context['profiles'] = profiles
        logger.info(f'[AgentTask] 接口画像加载: {len(profiles)} 个接口, cache={from_cache}')

        # Build embedding indexer (cached); may be None if deps unavailable
        _update_progress(task, 5, '构建语义索引')
        emb = ProjectIndexCache.get_embedding_indexer(project, profiles)
        if emb is None:
            logger.info('[AgentTask] embedding 索引不可用，使用纯 token 匹配模式')
        else:
            _update_progress(task, 8, '语义索引就绪')
        preselector = CandidatePreselector(embedding_indexer=emb)

        # Save Stage 0 checkpoint
        _save_checkpoint(task, 'index_init', {
            'profile_count': len(profiles),
            'from_cache': from_cache,
            'embedding_available': emb is not None,
        })

        _check_cancelled(cancel_event, task)

        # Stage 1: Step planning
        _begin_stage(task, 'step_planning')
        step_plan, step_llm = step_planner.plan(goal)
        steps = step_plan.get('steps', [])
        assertion_intents = step_plan.get('assertion_intents', [])
        context['steps'] = steps
        context['step_plan'] = step_plan
        context['llm_trace']['step_planning'] = step_llm
        _complete_stage(task, 'step_planning', step_plan)

        _check_cancelled(cancel_event, task)

        # Stage 1.5: Preselection (no LLM call)
        _update_progress(task, 30, '预选接口候选')
        feedback_memory = load_feedback_memory(project)
        candidates_by_step = preselector.select(steps, profiles, limit=candidate_limit, feedback_memory=feedback_memory)
        context['candidates_by_step'] = candidates_by_step

        _check_cancelled(cancel_event, task)

        # Stage 2: Interface matching
        _begin_stage(task, 'interface_matching')
        matches, match_llm = matcher.match(steps, candidates_by_step)
        context['matches'] = matches
        context['llm_trace']['interface_matching'] = match_llm
        _complete_stage(task, 'interface_matching', {
            'match_count': len([m for m in matches if m.get('selected_interface_id')]),
            'matches': matches,
        })

        _check_cancelled(cancel_event, task)

        # Stage 2.5: Response evidence (history first, then policy-controlled try-run)
        _update_progress(task, 60, '获取响应证据')
        response_evidence = evidence_resolver.resolve(
            matches,
            project=project,
            environment=environment,
            trial_policy=trial_policy,
        )
        response_samples = response_evidence['response_samples']
        context['response_samples'] = response_samples
        context['response_evidence'] = response_evidence

        _check_cancelled(cancel_event, task)

        # Stage 3: Dependency planning
        _begin_stage(task, 'dependency_planning')
        dependency_plan, dependency_llm = dependency_planner.plan(steps, matches, response_samples=response_samples)
        context['dependency_plan'] = dependency_plan
        context['llm_trace']['dependency_planning'] = dependency_llm
        parameter_requirements = parameter_inferer.infer(
            steps, matches, dependency_plan=dependency_plan, response_samples=response_samples,
        )
        context['parameter_requirements'] = parameter_requirements
        _complete_stage(task, 'dependency_planning', dependency_plan)

        _check_cancelled(cancel_event, task)

        # Stage 4: Assertion planning
        _begin_stage(task, 'assertion_planning')
        assertion_plan, assertion_llm = assertion_planner.plan(
            steps, matches, dependency_plan=dependency_plan, response_samples=response_samples, goal=goal,
            assertion_intents=assertion_intents,
        )
        context['assertion_plan'] = assertion_plan
        context['llm_trace']['assertion_planning'] = assertion_llm
        _complete_stage(task, 'assertion_planning', {'items': assertion_plan})

        _check_cancelled(cancel_event, task)

        # Stage 5: Build draft & validate (no LLM call)
        _update_progress(task, 95, '校验 & 生成草稿')
        chain_draft = builder.build(
            project,
            step_plan.get('goal') or goal,
            steps,
            matches,
            dependency_plan,
            response_samples=response_samples,
            assertion_plan=assertion_plan,
        )
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

        # Build final result
        result = {
            'mode': 'model_driven',
            'llm_trace': context['llm_trace'],
            'step_plan': step_plan,
            'steps': steps,
            'candidates_by_step': candidates_by_step,
            'matches': matches,
            'dependency_plan': dependency_plan,
            'parameter_requirements': parameter_requirements,
            'assertion_plan': assertion_plan,
            'response_evidence': context.get('response_evidence', {}),
            'chain_draft': chain_draft,
            'validation': validation,
            'warnings': validation.get('warnings', []) + context.get('response_evidence', {}).get('warnings', []),
            'questions': step_plan.get('questions', []) + context.get('response_evidence', {}).get('questions', []),
            'saved_chain_id': saved_chain.id if saved_chain else None,
            'project_id': project.id if project else None,
        }

        # Mark task completed
        _complete_all_plan_stages(task, result)
        task.status = AgentTask.STATUS_COMPLETED
        task.progress = 100
        task.current_step = '完成'
        task.result = result
        task.finished_at = datetime.now()
        task.save(update_fields=['status', 'progress', 'current_step', 'result', 'finished_at'])

    except AgentCancelledError:
        logger.info(f'[AgentTask] {task_id_str} was cancelled by user')
        # _check_cancelled already marks the task status

    except LLMError as exc:
        _mark_failed(task, f'{exc.message}', llm_error=exc)

    except Exception as exc:
        logger.exception(f'AgentTask {task_id_str} failed')
        _mark_failed(task, f'{type(exc).__name__}: {str(exc)[:500]}')


def _run_agent_task_from_checkpoint(task_id_str, cancel_event):
    """Resume a completed agent task from its checkpoint data.

    Restores LLM-intensive stage outputs (step_planning, interface_matching)
    from the original task's checkpoint, then re-runs from Stage 2.5
    (response_evidence) onwards with the updated trial_policy.

    This avoids re-running LLM calls that don't depend on write permissions.
    """
    try:
        task = AgentTask.objects.get(task_id=task_id_str)
    except AgentTask.DoesNotExist:
        logger.error(f'AgentTask (resume) {task_id_str} not found')
        return

    input_data = task.input_data or {}
    resume_from_id = input_data.get('resume_from_task_id')
    if not resume_from_id:
        _mark_failed(task, '缺少 resume_from_task_id，无法从断点恢复')
        return

    # Load original task checkpoint
    try:
        original_task = AgentTask.objects.get(task_id=resume_from_id)
    except AgentTask.DoesNotExist:
        _mark_failed(task, f'原始任务 {resume_from_id} 不存在，无法从断点恢复')
        return

    original_step_results = original_task.step_results or {}

    # Validate required checkpoint data exists
    for stage_key in ['step_planning', 'interface_matching']:
        stage_data = original_step_results.get(stage_key, {})
        if stage_data.get('status') != 'completed' or 'output' not in stage_data:
            _mark_failed(task, f'原始任务缺少 {stage_key} 阶段的断点数据，无法从断点恢复')
            return

    # Mark as running
    task.status = AgentTask.STATUS_RUNNING
    task.started_at = datetime.now()
    task.progress = 0
    task.current_step = '从断点恢复中...'
    task.save(update_fields=['status', 'started_at', 'progress', 'current_step'])

    # Restore context from original task checkpoint + original task result
    original_result = original_task.result or {}
    goal = input_data.get('goal', '') or original_result.get('step_plan', {}).get('goal', '')
    auto_save = input_data.get('auto_save', False)
    auto_execute = input_data.get('auto_execute', False)
    trial_policy = input_data.get('trial_policy') or {}
    project = task.project
    environment_id = input_data.get('environment_id')

    # Restore completed stage outputs
    sp_output = original_step_results['step_planning']['output']
    steps = sp_output.get('steps', [])
    assertion_intents = sp_output.get('assertion_intents', [])

    im_output = original_step_results['interface_matching']['output']
    matches = im_output.get('matches', [])

    candidates_by_step = original_result.get('candidates_by_step', [])
    llm_trace = original_result.get('llm_trace', {})

    logger.info(
        f'[AgentTask] 从断点恢复: task={task_id_str}, '
        f'original={resume_from_id}, steps={len(steps)}, matches={len(matches)}, '
        f'trial_policy_steps={trial_policy.get("authorized_step_indexes", [])}'
    )

    # Load environment
    environment = None
    if environment_id:
        try:
            from apps.api_debug.models import Environment
            environment = Environment.objects.get(id=environment_id, project=project)
            logger.info(f'[AgentTask] environment loaded: id={environment.id} name={environment.name}')
        except Exception as e:
            logger.warning(f'[AgentTask] environment_id={environment_id} not found: {e}')

    # Initialize services (only need non-LLM ones for stages we re-run, plus
    # the LLM-dependent ones for dependency/assertion planning)
    sampler = ResponseSampler()
    evidence_resolver = ResponseEvidenceResolver(sampler)
    llm = LLMGateway()
    dependency_planner = ModelDependencyPlanner(llm)
    parameter_inferer = ParameterRequirementInferer()
    assertion_planner = AssertionPlanner(llm)
    builder = ChainDraftBuilder()
    validator = PlanValidator()

    # Copy completed stage checkpoints to new task
    task.step_results = {}
    _save_checkpoint(task, 'index_init', original_step_results.get('index_init', {}).get('checkpoint', {}))
    task.step_results.update({
        'step_planning': {
            'status': 'completed',
            'progress': 100,
            'completed_at': datetime.now().isoformat(),
            'checkpoint': original_step_results['step_planning'].get('checkpoint'),
            'output': sp_output,
            'restored': True,
        },
        'interface_matching': {
            'status': 'completed',
            'progress': 100,
            'completed_at': datetime.now().isoformat(),
            'checkpoint': original_step_results['interface_matching'].get('checkpoint'),
            'output': im_output,
            'restored': True,
        },
    })
    task.save(update_fields=['step_results'])
    _save_checkpoint(task, 'step_planning_restored', {
        'source_task': resume_from_id,
        'step_count': len(steps),
        'assertion_count': len(assertion_intents),
        'note': '从断点恢复，跳过 LLM 步骤规划',
    })
    _save_checkpoint(task, 'interface_matching_restored', {
        'source_task': resume_from_id,
        'match_count': im_output.get('match_count', 0),
        'note': '从断点恢复，跳过 LLM 接口匹配',
    })

    # Set progress to show we're resuming from Stage 2.5
    task.progress = 55
    task.current_step = '从断点恢复 — 重新获取响应证据'
    task.save(update_fields=['progress', 'current_step'])

    try:
        _check_cancelled(cancel_event, task)

        # Stage 2.5: Response evidence — re-run with updated trial_policy
        _update_progress(task, 60, '获取响应证据（含授权接口）')
        response_evidence = evidence_resolver.resolve(
            matches,
            project=project,
            environment=environment,
            trial_policy=trial_policy,
        )
        response_samples = response_evidence['response_samples']

        _check_cancelled(cancel_event, task)

        # Stage 3: Dependency planning
        _begin_stage(task, 'dependency_planning')
        dependency_plan, dependency_llm = dependency_planner.plan(steps, matches, response_samples=response_samples)
        parameter_requirements = parameter_inferer.infer(
            steps, matches, dependency_plan=dependency_plan, response_samples=response_samples,
        )
        llm_trace['dependency_planning'] = dependency_llm
        _complete_stage(task, 'dependency_planning', dependency_plan)

        _check_cancelled(cancel_event, task)

        # Stage 4: Assertion planning
        _begin_stage(task, 'assertion_planning')
        assertion_plan, assertion_llm = assertion_planner.plan(
            steps, matches, dependency_plan=dependency_plan, response_samples=response_samples, goal=goal,
            assertion_intents=assertion_intents,
        )
        llm_trace['assertion_planning'] = assertion_llm
        _complete_stage(task, 'assertion_planning', {'items': assertion_plan})

        _check_cancelled(cancel_event, task)

        # Stage 5: Build draft & validate
        _update_progress(task, 95, '校验 & 生成草稿')
        chain_draft = builder.build(
            project,
            goal,
            steps,
            matches,
            dependency_plan,
            response_samples=response_samples,
            assertion_plan=assertion_plan,
        )

        from apps.api_debug.permissions import can_edit
        validation = validator.validate(steps, matches, dependency_plan, chain_draft, auto_execute=auto_execute)

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

        # Build final result (include restored data from original task)
        result = {
            'mode': 'model_driven',
            'resumed_from_task_id': resume_from_id,
            'llm_trace': llm_trace,
            'step_plan': sp_output,
            'steps': steps,
            'candidates_by_step': candidates_by_step,
            'matches': matches,
            'dependency_plan': dependency_plan,
            'parameter_requirements': parameter_requirements,
            'assertion_plan': assertion_plan,
            'response_evidence': response_evidence,
            'chain_draft': chain_draft,
            'validation': validation,
            'warnings': validation.get('warnings', []) + response_evidence.get('warnings', []),
            'questions': sp_output.get('questions', []) + response_evidence.get('questions', []),
            'saved_chain_id': saved_chain.id if saved_chain else None,
            'project_id': project.id if project else None,
        }

        # Mark task completed
        _complete_all_plan_stages(task, result)
        task.status = AgentTask.STATUS_COMPLETED
        task.progress = 100
        task.current_step = '完成'
        task.result = result
        task.finished_at = datetime.now()
        task.save(update_fields=['status', 'progress', 'current_step', 'result', 'finished_at'])

    except AgentCancelledError:
        logger.info(f'[AgentTask] (resume) {task_id_str} was cancelled by user')

    except LLMError as exc:
        _mark_failed(task, f'{exc.message}', llm_error=exc)

    except Exception as exc:
        logger.exception(f'AgentTask (resume) {task_id_str} failed')
        _mark_failed(task, f'{type(exc).__name__}: {str(exc)[:500]}')


def _begin_stage(task, stage_key):
    """Mark a stage as running in step_results and update progress."""
    stage = _get_stage(stage_key)
    if stage:
        task.current_step = stage['label']
        task.progress = stage['start']
    step_results = task.step_results or {}
    _complete_prior_running_stages(step_results, stage_key)
    step_results[stage_key] = {
        'status': 'running',
        'progress': stage['start'] if stage else 0,
        'started_at': datetime.now().isoformat(),
    }
    task.step_results = step_results
    task.save(update_fields=['current_step', 'progress', 'step_results'])


def _complete_stage(task, stage_key, output=None):
    """Mark a stage as completed in step_results and update progress.

    Persists full stage output as checkpoint data for potential resume.
    """
    stage = _get_stage(stage_key)
    if stage:
        task.progress = stage['end']
    step_results = task.step_results or {}
    step_results[stage_key] = {
        'status': 'completed',
        'progress': 100,
        'completed_at': datetime.now().isoformat(),
    }
    # Store both lightweight summary (for progress display) and full output (for resume)
    if output is not None:
        step_results[stage_key]['checkpoint'] = _make_checkpoint_summary(stage_key, output)
        step_results[stage_key]['output'] = output
    task.step_results = step_results
    task.save(update_fields=['progress', 'step_results'])


def _save_checkpoint(task, key, data):
    """Save arbitrary checkpoint data to step_results (non-stage data like index init)."""
    step_results = task.step_results or {}
    step_results[key] = {
        'status': 'completed',
        'progress': 100,
        'completed_at': datetime.now().isoformat(),
        'checkpoint': data,
    }
    task.step_results = step_results
    task.save(update_fields=['step_results'])


def _make_checkpoint_summary(stage_key, output):
    """Create a lightweight checkpoint summary from stage output.

    Full output lives in task.result (on completion).
    Checkpoint only stores key metadata for debugging / resume decisions.
    """
    if stage_key == 'step_planning':
        return {
            'step_count': len(output.get('steps', [])),
            'assertion_count': len(output.get('assertion_intents', [])),
        }
    elif stage_key == 'interface_matching':
        return {
            'match_count': output.get('match_count', 0),
        }
    elif stage_key == 'dependency_planning':
        mappings = output.get('mappings', [])
        return {
            'mapping_count': len(mappings),
        }
    elif stage_key == 'assertion_planning':
        items = output if isinstance(output, list) else output.get('items', [])
        return {
            'assertion_count': len(items),
        }
    return None


def _update_progress(task, progress, current_step):
    """Update progress and current_step without changing step_results."""
    if progress >= 95:
        step_results = task.step_results or {}
        for stage_key in ['step_planning', 'interface_matching', 'dependency_planning', 'assertion_planning']:
            if step_results.get(stage_key, {}).get('status') == 'running':
                step_results[stage_key] = {
                    **step_results[stage_key],
                    'status': 'completed',
                    'progress': 100,
                    'completed_at': datetime.now().isoformat(),
                }
        if step_results != (task.step_results or {}):
            task.step_results = step_results
    task.progress = progress
    task.current_step = current_step
    task.save(update_fields=['progress', 'current_step', 'step_results'])


def _get_stage(key):
    """Look up a stage by key."""
    for stage in STAGES:
        if stage['key'] == key:
            return stage
    return None


def _complete_prior_running_stages(step_results, next_stage_key):
    """When a later stage starts, any earlier running planning stage is done."""
    stage_order = ['step_planning', 'interface_matching', 'dependency_planning', 'assertion_planning', 'draft_and_validate']
    if next_stage_key not in stage_order:
        return
    next_index = stage_order.index(next_stage_key)
    now = datetime.now().isoformat()
    for stage_key in stage_order[:next_index]:
        value = step_results.get(stage_key)
        if isinstance(value, dict) and value.get('status') == 'running':
            value['status'] = 'completed'
            value['progress'] = 100
            value['completed_at'] = now


def _complete_all_plan_stages(task, result):
    """Normalize task step_results when a draft has been generated successfully."""
    step_results = task.step_results or {}
    now = datetime.now().isoformat()
    stage_outputs = {
        'step_planning': result.get('step_plan'),
        'interface_matching': {
            'match_count': len([m for m in result.get('matches', []) if m.get('selected_interface_id')]),
            'matches': result.get('matches', []),
        },
        'dependency_planning': result.get('dependency_plan'),
        'assertion_planning': {'items': result.get('assertion_plan', [])},
        'draft_and_validate': {
            'valid': result.get('validation', {}).get('valid'),
            'node_count': len(result.get('chain_draft', {}).get('nodes', [])),
            'edge_count': len(result.get('chain_draft', {}).get('edges', [])),
        },
    }
    for stage_key, output in stage_outputs.items():
        value = step_results.get(stage_key)
        if not isinstance(value, dict):
            value = {}
        value['status'] = 'completed'
        value['progress'] = 100
        value.setdefault('completed_at', now)
        if output is not None:
            value['output'] = output
            value['checkpoint'] = _make_checkpoint_summary(stage_key, output)
        step_results[stage_key] = value
    task.step_results = step_results
    task.save(update_fields=['step_results'])


def _mark_failed(task, error_message, llm_error=None):
    """Mark task as failed with error details. Persists partial results as checkpoint."""
    task.status = AgentTask.STATUS_FAILED
    task.error_message = error_message
    task.finished_at = datetime.now()

    # Mark the currently running stage as failed
    step_results = task.step_results or {}
    for key, value in step_results.items():
        if isinstance(value, dict) and value.get('status') == 'running':
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

        # Mark running stages as timeout
        step_results = task.step_results or {}
        for key, value in step_results.items():
            if isinstance(value, dict) and value.get('status') == 'running':
                step_results[key] = {
                    'status': 'timeout',
                    'error': '任务整体超时',
                }
        task.step_results = step_results
        task.save(update_fields=['status', 'error_message', 'finished_at', 'step_results'])
    except AgentTask.DoesNotExist:
        pass
