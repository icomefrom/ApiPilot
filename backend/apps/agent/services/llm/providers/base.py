import json
import re

from apps.agent.services.llm.errors import LLMResponseFormatError


class BaseLLMProvider:
    name = 'base'

    def __init__(self, *, base_url='', api_key='', model='', timeout=60):
        self.base_url = (base_url or '').rstrip('/')
        self.api_key = api_key or ''
        self.model = model or ''
        self.timeout = timeout

    def is_configured(self):
        return bool(self.base_url and self.model)

    def chat_json(self, messages, temperature=0.1):
        raise NotImplementedError

    def _parse_json_content(self, content):
        if isinstance(content, dict):
            return content
        if not content:
            raise LLMResponseFormatError('模型返回为空', provider=self.name)
        text = str(content).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.S)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            start = text.find('{')
            end = text.rfind('}')
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    pass
        raise LLMResponseFormatError('模型输出不是合法 JSON', provider=self.name, details={'content': text[:1000]})
