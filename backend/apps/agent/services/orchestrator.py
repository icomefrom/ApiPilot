from apps.api_debug.models import Chain
from apps.api_debug.permissions import can_edit
from apps.agent.services.building.chain_draft_builder import ChainDraftBuilder
from apps.agent.services.building.plan_validator import PlanValidator
from apps.agent.services.indexing.candidate_preselector import CandidatePreselector
from apps.agent.services.indexing.embedding_indexer import EmbeddingIndexer
from apps.agent.services.indexing.interface_indexer import InterfaceIndexer
from apps.agent.services.indexing.response_evidence_resolver import ResponseEvidenceResolver
from apps.agent.services.indexing.response_sampler import ResponseSampler
from apps.agent.services.llm.gateway import LLMGateway
from apps.agent.services.planning.assertion_planner import AssertionPlanner
from apps.agent.services.planning.dependency_planner import ModelDependencyPlanner
from apps.agent.services.planning.interface_matcher import InterfaceMatcher
from apps.agent.services.planning.step_planner import StepPlanner


class ModelDrivenAgentOrchestrator:
    def __init__(self, llm=None):
        self.llm = llm or LLMGateway()
        self.step_planner = StepPlanner(self.llm)
        self.indexer = InterfaceIndexer()
        self._embedding_indexer = EmbeddingIndexer(top_k=CandidatePreselector.EMBEDDING_TOP_K)
        self.preselector = CandidatePreselector(embedding_indexer=self._embedding_indexer)
        self.matcher = InterfaceMatcher(self.llm)
        self.sampler = ResponseSampler()
        self.evidence_resolver = ResponseEvidenceResolver(self.sampler)
        self.dependency_planner = ModelDependencyPlanner(self.llm)
        self.assertion_planner = AssertionPlanner(self.llm)
        self.builder = ChainDraftBuilder()
        self.validator = PlanValidator()

    def plan(self, *, user, project, goal, auto_save=False, auto_execute=False, candidate_limit=20, environment=None, trial_policy=None):
        step_plan, step_llm = self.step_planner.plan(goal)
        steps = step_plan.get('steps', [])
        assertion_intents = step_plan.get('assertion_intents', [])
        profiles = self.indexer.build_profiles(project)
        candidates_by_step = self.preselector.select(steps, profiles, limit=candidate_limit)
        matches, match_llm = self.matcher.match(steps, candidates_by_step)
        response_evidence = self.evidence_resolver.resolve(
            matches,
            project=project,
            environment=environment,
            trial_policy=trial_policy or {},
        )
        response_samples = response_evidence['response_samples']
        dependency_plan, dependency_llm = self.dependency_planner.plan(steps, matches, response_samples=response_samples)
        assertion_plan, assertion_llm = self.assertion_planner.plan(
            steps, matches, dependency_plan=dependency_plan, response_samples=response_samples, goal=goal,
            assertion_intents=assertion_intents,
        )
        chain_draft = self.builder.build(
            project,
            step_plan.get('goal') or goal,
            steps,
            matches,
            dependency_plan,
            response_samples=response_samples,
            assertion_plan=assertion_plan,
        )
        validation = self.validator.validate(steps, matches, dependency_plan, chain_draft, auto_execute=auto_execute)

        saved_chain = None
        if auto_save:
            if not can_edit(user, project):
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
                    created_by=user,
                )

        warnings = validation.get('warnings', [])
        return {
            'mode': 'model_driven',
            'llm_trace': {
                'step_planning': step_llm,
                'interface_matching': match_llm,
                'dependency_planning': dependency_llm,
                'assertion_planning': assertion_llm,
            },
            'step_plan': step_plan,
            'steps': steps,
            'candidates_by_step': candidates_by_step,
            'matches': matches,
            'dependency_plan': dependency_plan,
            'assertion_plan': assertion_plan,
            'response_evidence': response_evidence,
            'chain_draft': chain_draft,
            'validation': validation,
            'warnings': warnings + response_evidence.get('warnings', []),
            'questions': step_plan.get('questions', []) + response_evidence.get('questions', []),
            'saved_chain_id': saved_chain.id if saved_chain else None,
        }


OpenSourceAgentOrchestrator = ModelDrivenAgentOrchestrator
