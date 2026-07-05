import requests

from apps.agent.services.llm.errors import LLMError
from .base import BaseLLMProvider


class OllamaProvider(BaseLLMProvider):
    name = 'ollama'

    def chat_json(self, messages, temperature=0.1):
        if not self.is_configured():
            raise LLMError('Ollama 模型未配置', provider=self.name)
        payload = {
            'model': self.model,
            'messages': messages,
            'stream': False,
            'format': 'json',
            'options': {'temperature': temperature},
        }
        try:
            response = requests.post(
                f'{self.base_url}/api/chat',
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            content = data.get('message', {}).get('content', '')
            return self._parse_json_content(content)
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f'Ollama 调用失败: {exc}', provider=self.name) from exc
