"""
L4: Knowledge Base（知识库）
使用向量数据库进行语义检索
"""
import hashlib
from typing import Any, Dict, List, Optional

from config import settings


class KnowledgeBase:
    """
    知识库 - L4层
    使用向量数据库进行语义检索
    支持RAG (Retrieval-Augmented Generation)
    """

    def __init__(
        self,
        vector_db_client=None,
        embedding_model=None,
    ):
        self.vector_db = vector_db_client
        self.embedding_model = embedding_model
        self._initialized = False
        self._in_memory_store: Dict[str, Dict[str, Any]] = {}
        self._use_memory_fallback = True

    async def _ensure_initialized(self) -> None:
        """确保向量数据库初始化"""
        if self._initialized:
            return

        if settings.VECTOR_DB_URL and self.vector_db is None:
            try:
                # 尝试初始化Qdrant客户端
                from qdrant_client import QdrantClient
                self.vector_db = QdrantClient(url=settings.VECTOR_DB_URL)
                self._use_memory_fallback = False
            except ImportError:
                pass

        if settings.EMBEDDING_MODEL and self.embedding_model is None:
            try:
                # 尝试初始化嵌入模型
                from openai import AsyncOpenAI
                self._openai_client = AsyncOpenAI()
            except Exception:
                pass

        self._initialized = True

    async def _get_embedding(self, text: str) -> List[float]:
        """获取文本的嵌入向量"""
        if hasattr(self, "_openai_client"):
            try:
                response = await self._openai_client.embeddings.create(
                    model=settings.EMBEDDING_MODEL,
                    input=text,
                )
                return response.data[0].embedding
            except Exception:
                pass

        # 简单的哈希嵌入作为fallback
        hash_bytes = hashlib.sha256(text.encode()).digest()
        embedding = [float(b) / 255.0 for b in hash_bytes[:32]]
        # 扩展到512维
        while len(embedding) < 512:
            embedding.extend(embedding[: min(512 - len(embedding), len(embedding))])
        return embedding[:512]

    async def add_knowledge(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        doc_id: Optional[str] = None,
    ) -> str:
        """添加知识到知识库"""
        await self._ensure_initialized()

        if doc_id is None:
            doc_id = hashlib.md5(content.encode()).hexdigest()

        if self._use_memory_fallback:
            self._in_memory_store[doc_id] = {
                "content": content,
                "metadata": metadata or {},
            }
            return doc_id

        try:
            embedding = await self._get_embedding(content)

            self.vector_db.upsert(
                collection_name="knowledge",
                points=[
                    {
                        "id": doc_id,
                        "vector": embedding,
                        "payload": {
                            "content": content,
                            "metadata": metadata or {},
                        },
                    }
                ],
            )
            return doc_id
        except Exception:
            # Fallback到内存存储
            self._in_memory_store[doc_id] = {
                "content": content,
                "metadata": metadata or {},
            }
            return doc_id

    async def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """搜索知识"""
        await self._ensure_initialized()

        if self._use_memory_fallback:
            # 简单的关键词匹配作为fallback
            results = []
            query_lower = query.lower()
            for doc_id, data in self._in_memory_store.items():
                if query_lower in data["content"].lower():
                    results.append({
                        "id": doc_id,
                        "content": data["content"],
                        "metadata": data["metadata"],
                        "score": 0.8,  # 简单评分
                    })
            return results[:top_k]

        try:
            query_embedding = await self._get_embedding(query)

            search_result = self.vector_db.search(
                collection_name="knowledge",
                query_vector=query_embedding,
                limit=top_k,
                query_filter=filters,
            )

            return [
                {
                    "id": str(hit.id),
                    "content": hit.payload.get("content", ""),
                    "metadata": hit.payload.get("metadata", {}),
                    "score": hit.score,
                }
                for hit in search_result
            ]
        except Exception:
            return []

    async def retrieve_with_context(
        self,
        query: str,
        top_k: int = 5,
    ) -> tuple[str, List[Dict[str, Any]]]:
        """检索并构建上下文"""
        results = await self.search(query, top_k)

        if not results:
            return "", []

        context_parts = []
        for i, r in enumerate(results):
            context_parts.append(f"【知识{i+1}】\n{r['content']}")

        context = "\n\n".join(context_parts)
        return context, results

    async def delete_knowledge(self, doc_id: str) -> bool:
        """删除知识"""
        await self._ensure_initialized()

        if self._use_memory_fallback:
            if doc_id in self._in_memory_store:
                del self._in_memory_store[doc_id]
                return True
            return False

        try:
            self.vector_db.delete(
                collection_name="knowledge",
                points_selector=[doc_id],
            )
            return True
        except Exception:
            return False

    async def batch_add_knowledge(
        self,
        documents: List[Dict[str, Any]],
    ) -> List[str]:
        """批量添加知识"""
        doc_ids = []
        for doc in documents:
            doc_id = await self.add_knowledge(
                content=doc["content"],
                metadata=doc.get("metadata"),
                doc_id=doc.get("id"),
            )
            doc_ids.append(doc_id)
        return doc_ids

    async def get_stats(self) -> Dict[str, Any]:
        """获取知识库统计信息"""
        await self._ensure_initialized()

        if self._use_memory_fallback:
            return {
                "total_documents": len(self._in_memory_store),
                "storage_type": "memory",
            }

        try:
            collection_info = self.vector_db.get_collection("knowledge")
            return {
                "total_documents": collection_info.points_count,
                "storage_type": "vector_db",
            }
        except Exception:
            return {
                "total_documents": len(self._in_memory_store),
                "storage_type": "memory_fallback",
            }
