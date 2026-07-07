"""
语义召回索引器 — 基于 gte-multilingual-base embedding + FAISS

职责:
  1. 对所有接口的 name + description 构建 embedding 索引
  2. 对查询文本做 embedding，通过 FAISS 检索 Top-K 语义最相似的接口
  3. 与 CandidatePreselector 的 token 匹配互补，解决口语化/同义词零交集问题
"""
import logging
import os

logger = logging.getLogger(__name__)

# 全局单例，避免重复加载模型
_model = None

# ModelScope 模型 ID（国内推荐，加载速度快）
_MODELSCOPE_MODEL_ID = os.environ.get(
    'AGENT_EMBEDDING_MODELSCOPE_ID', 'iic/gte_sentence-embedding_multilingual-base'
)

# HuggingFace 模型 ID（外网环境可用，国内很慢）
_HF_MODEL_NAME = os.environ.get(
    'AGENT_EMBEDDING_MODEL', 'Alibaba-NLP/gte-multilingual-base'
)

# 模型加载策略: modelscope (默认，国内快) / huggingface (外网) / auto (先 ModelScope 后 HF)
_EMBEDDING_SOURCE = os.environ.get(
    'AGENT_EMBEDDING_SOURCE', 'modelscope'
).lower()


def _fix_position_ids(model):
    """
    修复 transformers 5.x 与 gte-multilingual-base (NewModel) 的兼容性问题。

    NewModel 使用 register_buffer("position_ids", ..., persistent=False)，
    在 transformers 5.x 的 from_pretrained 加载后，persistent=False 的
    buffer 不会被正确重新初始化，导致 position_ids 包含垃圾值，推理时
    出现 IndexError。此函数手动重新初始化 position_ids。
    """
    try:
        import torch
        auto_model = model[0].auto_model
        if hasattr(auto_model, 'embeddings') and hasattr(auto_model.embeddings, 'position_ids'):
            max_pos = getattr(auto_model.config, 'max_position_embeddings', 8192)
            auto_model.embeddings.register_buffer(
                'position_ids', torch.arange(max_pos), persistent=False
            )
            logger.info(
                '[EmbeddingIndexer] 修复 position_ids (max=%d), 前 5 项: %s',
                max_pos, auto_model.embeddings.position_ids[:5].tolist(),
            )
    except Exception as e:
        logger.warning('[EmbeddingIndexer] 修复 position_ids 失败: %s', e)


def _load_from_modelscope():
    """从 ModelScope 加载模型（国内推荐，速度快）。"""
    from modelscope.hub.snapshot_download import snapshot_download as ms_snapshot_download
    from sentence_transformers import SentenceTransformer

    print(f'[EmbeddingIndexer] Loading embedding model from ModelScope: {_MODELSCOPE_MODEL_ID}', flush=True)
    local_dir = ms_snapshot_download(_MODELSCOPE_MODEL_ID)
    print(f'[EmbeddingIndexer] ModelScope model downloaded to: {local_dir}', flush=True)
    model = SentenceTransformer(local_dir, trust_remote_code=True)
    _fix_position_ids(model)
    print(f'[EmbeddingIndexer] Embedding model loaded from ModelScope: {_MODELSCOPE_MODEL_ID}', flush=True)
    return model


def _load_from_huggingface():
    """从 HuggingFace 加载模型（外网环境用，国内很慢）。"""
    from sentence_transformers import SentenceTransformer

    print(f'[EmbeddingIndexer] Loading embedding model from HuggingFace: {_HF_MODEL_NAME}', flush=True)
    model = SentenceTransformer(_HF_MODEL_NAME, trust_remote_code=True)
    _fix_position_ids(model)
    print(f'[EmbeddingIndexer] Embedding model loaded from HuggingFace: {_HF_MODEL_NAME}', flush=True)
    return model


def _get_model():
    global _model
    if _model is not None:
        return _model

    # 根据策略选择加载方式
    source = _EMBEDDING_SOURCE

    # 策略: modelscope — 直接从 ModelScope 加载（国内推荐）
    if source == 'modelscope':
        try:
            _model = _load_from_modelscope()
            return _model
        except ImportError:
            logger.warning(
                '[EmbeddingIndexer] modelscope 未安装，请 pip install modelscope。'
                '尝试降级到 HuggingFace...',
            )
            print('[EmbeddingIndexer] modelscope 未安装，尝试降级到 HuggingFace...', flush=True)
        except Exception as e:
            logger.warning(
                '[EmbeddingIndexer] ModelScope 加载失败 (%s: %s)，尝试降级到 HuggingFace...',
                type(e).__name__, e,
            )
            print(f'[EmbeddingIndexer] ModelScope 加载失败 ({type(e).__name__}: {e})，尝试降级到 HuggingFace...', flush=True)

        # ModelScope 失败，降级到 HuggingFace
        try:
            _model = _load_from_huggingface()
            return _model
        except Exception as e:
            logger.warning(
                '[EmbeddingIndexer] HuggingFace 加载也失败 (%s: %s)，embedding 不可用',
                type(e).__name__, e,
            )
            print(f'[EmbeddingIndexer] HuggingFace 加载也失败 ({type(e).__name__}: {e})，embedding 不可用', flush=True)
        return None

    # 策略: huggingface — 直接从 HuggingFace 加载（外网环境）
    if source == 'huggingface':
        try:
            _model = _load_from_huggingface()
            return _model
        except Exception as e:
            logger.warning(
                '[EmbeddingIndexer] HuggingFace 加载失败 (%s: %s)，尝试降级到 ModelScope...',
                type(e).__name__, e,
            )
            print(f'[EmbeddingIndexer] HuggingFace 加载失败 ({type(e).__name__}: {e})，尝试降级到 ModelScope...', flush=True)

        try:
            _model = _load_from_modelscope()
            return _model
        except Exception as e:
            logger.warning(
                '[EmbeddingIndexer] ModelScope 加载也失败 (%s: %s)，embedding 不可用',
                type(e).__name__, e,
            )
            print(f'[EmbeddingIndexer] ModelScope 加载也失败 ({type(e).__name__}: {e})，embedding 不可用', flush=True)
        return None

    # 策略: auto — 先 ModelScope 后 HuggingFace
    try:
        _model = _load_from_modelscope()
        return _model
    except Exception as e:
        logger.warning('[EmbeddingIndexer] ModelScope 加载失败 (%s: %s)，尝试 HuggingFace...', type(e).__name__, e)

    try:
        _model = _load_from_huggingface()
        return _model
    except Exception as e:
        logger.warning('[EmbeddingIndexer] HuggingFace 加载也失败 (%s: %s)，embedding 不可用', type(e).__name__, e)

    return None


class EmbeddingIndexer:
    """基于 embedding 的接口语义召回索引。"""

    # 语义召回默认返回的候选数
    DEFAULT_TOP_K = 30

    # 语义最低相似度阈值，低于此值不作为候选
    MIN_SIMILARITY = 0.15

    def __init__(self, top_k=None, min_similarity=None):
        self.top_k = top_k or self.DEFAULT_TOP_K
        self.min_similarity = min_similarity or self.MIN_SIMILARITY
        self._index = None        # FAISS 索引
        self._profile_map = {}    # index -> profile dict (不含 tokens)
        self._id_to_idx = {}      # interface_id -> faiss index
        self._built = False

    # ------------------------------------------------------------------
    # 索引构建
    # ------------------------------------------------------------------

    def build(self, profiles):
        """
        对 profiles 列表构建 FAISS 索引。

        profiles: 与 InterfaceIndexer.build_profile 输出格式一致的 dict 列表
        """
        import numpy as np

        if not profiles:
            self._built = False
            return

        model = _get_model()
        if model is None:
            logger.warning('[EmbeddingIndexer] 模型不可用，跳过 embedding 索引构建')
            self._built = False
            return

        # 拼接 name + description 作为 embedding 输入
        texts = []
        for p in profiles:
            name = (p.get('name') or '').strip()
            desc = (p.get('description') or '').strip()
            # name 重复两次以增强权重
            text = f'{name} {name} {desc}' if desc else f'{name} {name}'
            texts.append(text)

        logger.info('Building embedding index for %d profiles...', len(profiles))
        embeddings = model.encode(
            texts, normalize_embeddings=True,
            show_progress_bar=False, batch_size=64,
        )
        embeddings = np.array(embeddings, dtype='float32')

        # 构建 FAISS 索引 (Inner Product = cosine similarity because normalized)
        import faiss
        dim = embeddings.shape[1]
        self._index = faiss.IndexFlatIP(dim)
        self._index.add(embeddings)

        # 保存 profile 映射
        self._profile_map = {}
        self._id_to_idx = {}
        for i, p in enumerate(profiles):
            clean = {k: v for k, v in p.items() if k != 'tokens'}
            self._profile_map[i] = clean
            self._id_to_idx[p.get('interface_id')] = i

        self._built = True
        logger.info(
            'Embedding index built: %d profiles, dim=%d',
            len(profiles), dim,
        )

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def search(self, query, top_k=None):
        """
        对查询文本做语义召回。

        返回: list of dict, 每个 dict 含 interface 信息 + semantic_score + semantic_rank
        """
        import numpy as np

        if not self._built or not self._index:
            return []

        top_k = top_k or self.top_k
        top_k = min(top_k, self._index.ntotal)

        model = _get_model()
        query_emb = model.encode(
            [query], normalize_embeddings=True, show_progress_bar=False,
        )
        query_emb = np.array(query_emb, dtype='float32')

        scores, indices = self._index.search(query_emb, top_k)

        results = []
        for rank, (idx, score) in enumerate(zip(indices[0], scores[0]), 1):
            if score < self.min_similarity:
                continue
            profile = self._profile_map.get(int(idx))
            if not profile:
                continue
            item = dict(profile)
            item['semantic_score'] = round(float(score), 4)
            item['semantic_rank'] = rank
            results.append(item)

        return results

    def get_semantic_scores_batch(self, query):
        """
        一次性编码 query，返回 {interface_id: semantic_score} 字典。
        比 per-profile 调用 get_semantic_score() 快 ~300x（只编码一次）。
        """
        if not self._built or not self._index:
            return {}
        import numpy as np
        model = _get_model()
        query_emb = model.encode(
            [query], normalize_embeddings=True, show_progress_bar=False,
        )
        query_emb = np.array(query_emb, dtype='float32')
        # 对全量向量做点积，一次算完
        all_vecs = self._index.reconstruct_n(0, self._index.ntotal)
        scores = np.dot(all_vecs, query_emb[0])
        result = {}
        for iid, idx in self._id_to_idx.items():
            result[iid] = round(max(0.0, float(scores[idx])), 4)
        return result

    def get_semantic_score(self, query, interface_id):
        """
        查询某个 interface_id 对应 query 的语义相似度。
        用于与 token pre_score 合并。
        注意: 批量查询时优先使用 get_semantic_scores_batch() 以避免重复编码。
        """
        if not self._built or interface_id not in self._id_to_idx:
            return 0.0
        import numpy as np
        model = _get_model()
        query_emb = model.encode(
            [query], normalize_embeddings=True, show_progress_bar=False,
        )
        idx = self._id_to_idx[interface_id]
        # 直接从 FAISS 索引取对应向量做点积
        vec = self._index.reconstruct(int(idx))
        score = float(np.dot(query_emb[0], vec))
        return round(max(0.0, score), 4)

    @property
    def is_built(self):
        return self._built