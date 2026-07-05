import requests

from apps.agent.services.llm.errors import LLMError
from .base import BaseLLMProvider


class OpenAICompatibleProvider(BaseLLMProvider):
    name = 'openai_compatible'

    def is_configured(self):
        return bool(self.base_url and self.model and self.api_key)

    def chat_json(self, messages, temperature=0.1):
        if not self.is_configured():
            raise LLMError('OpenAI-Compatible 模型未配置', provider=self.name)
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
        }
        payload = {
            'model': self.model,
            'messages': messages,
            'temperature': temperature,
            'response_format': {'type': 'json_object'},
        }
        try:
            response = requests.post(
                f'{self.base_url}/chat/completions',
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            content = data['choices'][0]['message']['content']
            return self._parse_json_content(content)
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f'OpenAI-Compatible 调用失败: {exc}', provider=self.name) from exc
