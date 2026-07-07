import logging
import sys

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class AgentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.agent'
    verbose_name = 'Agent 编排'

    def ready(self):
        from apps.agent.services.indexing.project_index_cache import register_interface_signals
        register_interface_signals()

        # Pre-warm embedding model in background thread to avoid cold-start delay
        self._prewarm_embedding_model()

    def _prewarm_embedding_model(self):
        """Load embedding model in a background thread on app startup.

        The first agent task otherwise pays a 10-30s penalty loading the model.
        Pre-warming ensures the model is ready when the first request arrives.
        """
        import os
        import threading

        # Allow disabling pre-warming via env var
        if os.environ.get('AGENT_EMBEDDING_PREWARM', 'true').lower() in ('false', '0', 'no'):
            print('[AgentConfig] Embedding model pre-warming disabled by AGENT_EMBEDDING_PREWARM=false', flush=True)
            return

        def _warm():
            try:
                print('[AgentConfig] Pre-warming embedding model...', flush=True)
                from apps.agent.services.indexing.embedding_indexer import _get_model
                model = _get_model()
                if model is not None:
                    print('[AgentConfig] Embedding model pre-warmed successfully', flush=True)
                else:
                    print('[AgentConfig] WARNING: Embedding model pre-warming returned None (will fallback to token-only matching)', flush=True)
            except Exception as e:
                print(f'[AgentConfig] WARNING: Embedding model pre-warming failed: {e}', flush=True)

        thread = threading.Thread(target=_warm, name='embedding-prewarm', daemon=True)
        thread.start()
