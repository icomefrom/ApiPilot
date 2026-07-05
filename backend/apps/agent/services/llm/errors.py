class LLMError(Exception):
    error_code = 'LLM_ERROR'

    def __init__(self, message, *, provider=None, details=None):
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.details = details or {}


class LLMUnavailableError(LLMError):
    error_code = 'LLM_UNAVAILABLE'


class LLMResponseFormatError(LLMError):
    error_code = 'LLM_RESPONSE_FORMAT_ERROR'
