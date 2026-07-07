import os

from django.conf import settings

from apps.agent.services.llm.errors import LLMError, LLMUnavailableError
from apps.agent.services.llm.providers.ollama import OllamaProvider
from apps.agent.services.llm.providers.openai_compatible import OpenAICompatibleProvider


class LLMGateway:
    """模型网关：OpenAI-Compatible 优先，本地 Ollama 兜底。"""

    def __init__(self):
        timeout = int(os.environ.get('AGENT_LLM_TIMEOUT', getattr(settings, 'AGENT_LLM_TIMEOUT', 60)))
        self.primary = OpenAICompatibleProvider(
            base_url=os.environ.get('AGENT_OPENAI_BASE_URL', getattr(settings, 'AGENT_OPENAI_BASE_URL', '')),
            api_key=os.environ.get('AGENT_OPENAI_API_KEY', getattr(settings, 'AGENT_OPENAI_API_KEY', '')),
            model=os.environ.get('AGENT_OPENAI_MODEL', getattr(settings, 'AGENT_OPENAI_MODEL', '')),
            timeout=timeout,
        )
        self.fallback = OllamaProvider(
            base_url=os.environ.get('AGENT_OLLAMA_BASE_URL', getattr(settings, 'AGENT_OLLAMA_BASE_URL', 'http://localhost:11434')),
            model=os.environ.get('AGENT_OLLAMA_MODEL', getattr(settings, 'AGENT_OLLAMA_MODEL', '')),
            timeout=timeout,
        )

    def chat_json(self, messages, *, temperature=0.1):
        errors = []
        for provider in self._providers():
            try:
                data = provider.chat_json(messages, temperature=temperature)
                return {'provider': provider.name, 'model': provider.model, 'data': data}
            except LLMError as exc:
                errors.append({
                    'provider': exc.provider or provider.name,
                    'message': exc.message,
                    'code': getattr(exc, 'error_code', 'LLM_ERROR'),
                })
        raise LLMUnavailableError(
            'Agent 需要模型推理。OpenAI-Compatible 不可用，Ollama 也不可用，请配置模型或启动 Ollama。',
            details={'errors': errors},
        )

    def _providers(self):
        providers = []
        if self.primary.is_configured():
            providers.append(self.primary)
        providers.append(self.fallback)
        return providers
