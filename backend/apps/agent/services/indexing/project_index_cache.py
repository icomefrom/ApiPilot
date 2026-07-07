"""
项目级接口画像缓存 + Embedding 索引缓存

设计：
- _project_caches: {project_id: {profiles, embedding_indexer, version, built_at}}
- version 由 ApiInterface 的 max(updated_at) 决定
- 项目接口增删改 → Django signal 失效对应项目缓存
- 有效期 TTL = 600 秒（可配置），超时也失效
- 线程安全：用 threading.Lock 保护写操作
"""
import logging
import threading
import time
from datetime import datetime

from django.conf import settings

from apps.agent.services.indexing.interface_indexer import InterfaceIndexer
from apps.agent.services.indexing.embedding_indexer import EmbeddingIndexer

logger = logging.getLogger(__name__)

# 缓存 TTL（秒），默认 10 分钟
_CACHE_TTL = getattr(settings, 'AGENT_INDEX_CACHE_TTL', 600)

# embedding 依赖可用性标记（只检测一次）
_embedding_deps_available = None


def _embedding_available():
    """检查 embedding 依赖（numpy, faiss, sentence_transformers）是否可用。"""
    global _embedding_deps_available
    if _embedding_deps_available is None:
        try:
            import numpy  # noqa: F401
            import faiss  # noqa: F401
            from sentence_transformers import SentenceTransformer  # noqa: F401
            _embedding_deps_available = True
        except ImportError as e:
            logger.info('[ProjectIndexCache] embedding 依赖不可用: %s', e)
            _embedding_deps_available = False
    return _embedding_deps_available

# 全局缓存锁
_cache_lock = threading.Lock()

# {project_id: {profiles, embedding_indexer, version, built_at}}
_project_caches = {}


class ProjectIndexCache:
    """项目级接口画像 + Embedding 索引缓存。"""

    @staticmethod
    def get_profiles(project, force_rebuild=False):
        """获取项目接口画像，优先从缓存读取。

        Args:
            project: Project 实例
            force_rebuild: 强制重建

        Returns:
            (profiles, from_cache)
        """
        project_id = project.id
        now = time.time()

        # 计算当前版本 = 接口表最新更新时间
        from apps.api_debug.models import ApiInterface
        version = _get_interface_version(project_id)

        cache = _project_caches.get(project_id)

        if not force_rebuild and cache:
            expired = (now - cache['built_at']) > _CACHE_TTL
            version_changed = cache['version'] != version
            if not expired and not version_changed:
                return cache['profiles'], True

        # 需要重建
        indexer = InterfaceIndexer()
        profiles = indexer.build_profiles(project)

        with _cache_lock:
            _project_caches[project_id] = {
                'profiles': profiles,
                'embedding_indexer': None,
                'version': version,
                'built_at': now,
            }

        logger.info(f'[ProjectIndexCache] 重建项目 {project_id} 画像缓存: {len(profiles)} 个接口, version={version}')
        return profiles, False

    @staticmethod
    def get_embedding_indexer(project, profiles=None):
        """获取项目的 Embedding 索引，优先从缓存读取。

        当 numpy/faiss/sentence-transformers 不可用时，返回 None 并记录警告，
        上游将以纯 token 匹配模式降级运行。

        Args:
            project: Project 实例
            profiles: 可选，如果不传则自动获取

        Returns:
            EmbeddingIndexer 实例（已 build），或 None（依赖不可用时）
        """
        # 检查 embedding 依赖是否可用
        if not _embedding_available():
            logger.warning(
                '[ProjectIndexCache] embedding 依赖（numpy/faiss/sentence-transformers）不可用，'
                '将使用纯 token 匹配模式'
            )
            return None

        project_id = project.id
        cache = _project_caches.get(project_id)

        if cache and cache.get('embedding_indexer') and cache['embedding_indexer'].is_built:
            return cache['embedding_indexer']

        # 需要 profiles
        if profiles is None:
            profiles, _ = ProjectIndexCache.get_profiles(project)

        # 构建 embedding 索引
        try:
            emb = EmbeddingIndexer(top_k=30)
            if profiles:
                emb.build(profiles)
        except Exception as e:
            logger.warning(
                '[ProjectIndexCache] 构建 Embedding 索引失败 (%s: %s)，将使用纯 token 匹配模式',
                type(e).__name__, e,
            )
            return None

        with _cache_lock:
            # 确保 cache 存在
            if project_id not in _project_caches:
                _project_caches[project_id] = {
                    'profiles': profiles,
                    'embedding_indexer': emb,
                    'version': _get_interface_version(project_id),
                    'built_at': time.time(),
                }
            else:
                _project_caches[project_id]['embedding_indexer'] = emb

        logger.info(f'[ProjectIndexCache] 重建项目 {project_id} Embedding 索引: {len(profiles)} 个接口')
        return emb

    @staticmethod
    def invalidate(project_id):
        """失效指定项目的缓存（接口变更时调用）。"""
        with _cache_lock:
            if project_id in _project_caches:
                old = _project_caches.pop(project_id)
                emb = old.get('embedding_indexer')
                emb_info = f', embedding_built={emb.is_built if emb else "N/A"}' if emb else ''
                logger.info(f'[ProjectIndexCache] 失效项目 {project_id} 缓存 (profiles={len(old.get("profiles", []))}{emb_info})')

    @staticmethod
    def invalidate_all():
        """失效所有项目缓存。"""
        with _cache_lock:
            count = len(_project_caches)
            _project_caches.clear()
            logger.info(f'[ProjectIndexCache] 失效全部缓存 ({count} 个项目)')

    @staticmethod
    def get_cache_stats():
        """获取缓存统计信息，用于调试。"""
        now = time.time()
        stats = {}
        for pid, cache in _project_caches.items():
            emb = cache.get('embedding_indexer')
            stats[pid] = {
                'profile_count': len(cache.get('profiles', [])),
                'embedding_built': emb.is_built if emb else False,
                'version': cache.get('version'),
                'age_seconds': int(now - cache.get('built_at', now)),
                'ttl_remaining': max(0, int(_CACHE_TTL - (now - cache.get('built_at', now)))),
            }
        return stats


def _get_interface_version(project_id):
    """获取项目接口版本标识（用最新 updated_at 时间戳）。

    Returns:
        str: 版本标识，如 "2026-07-06T07:30:00.123456+00:00" 或 "empty"
    """
    from apps.api_debug.models import ApiInterface
    result = ApiInterface.objects.filter(project_id=project_id).order_by('-updated_at').values_list('updated_at', flat=True).first()
    if result is None:
        return 'empty'
    return str(result)


# ---------------------------------------------------------------------------
# Django Signal: 接口增删改 → 自动失效缓存
# ---------------------------------------------------------------------------

def _on_interface_change(sender, instance, **kwargs):
    """ApiInterface post_save / post_delete / m2m_changed 信号处理。"""
    project_id = instance.project_id
    if project_id:
        ProjectIndexCache.invalidate(project_id)


def _on_interface_delete(sender, instance, **kwargs):
    """ApiInterface post_delete 信号处理。"""
    project_id = instance.project_id
    if project_id:
        ProjectIndexCache.invalidate(project_id)


def register_interface_signals():
    """注册接口缓存失效信号。在 AppConfig.ready() 中调用。"""
    from apps.api_debug.models import ApiInterface
    from django.db.models.signals import post_save, post_delete

    post_save.connect(_on_interface_change, sender=ApiInterface, dispatch_uid='agent_cache_interface_save')
    post_delete.connect(_on_interface_delete, sender=ApiInterface, dispatch_uid='agent_cache_interface_delete')
    logger.info('[ProjectIndexCache] 已注册 ApiInterface 信号 -> 缓存失效')