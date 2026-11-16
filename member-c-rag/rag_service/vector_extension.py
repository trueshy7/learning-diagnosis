"""可选实验适配器；默认 HTTP 服务尚未接入此类，不会自动创建向量模型。"""
from typing import Protocol


class EmbeddingAdapter(Protocol):
    """由成员 C 显式实现：本地已安装模型或团队批准的远程嵌入服务。"""

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class ChromaExperiment:
    """仅处理显式提供的向量；不启用 Chroma 默认 embedding_function。"""

    def __init__(self, path: str, adapter: EmbeddingAdapter, collection_name: str = "learning_chunks"):
        import chromadb  # 可选依赖，默认服务不会导入。

        self.adapter = adapter
        self.client = chromadb.PersistentClient(path=path)
        self.collection = self.client.get_or_create_collection(
            name=collection_name, embedding_function=None,
        )

    def upsert(self, ids: list[str], texts: list[str], metadatas: list[dict]) -> None:
        vectors = self.adapter.embed_documents(texts)
        if len(vectors) != len(texts):
            raise ValueError("嵌入向量数量必须与文本数量一致")
        self.collection.upsert(ids=ids, documents=texts, metadatas=metadatas, embeddings=vectors)

    def query(self, text: str, top_k: int = 5, where: dict | None = None) -> dict:
        if not 1 <= top_k <= 10:
            raise ValueError("top_k 必须在 1–10 之间")
        vector = self.adapter.embed_query(text)
        return self.collection.query(query_embeddings=[vector], n_results=top_k, where=where)

    def delete_resource(self, resource_id: str) -> None:
        self.collection.delete(where={"resource_id": resource_id})


# TODO：为服务增加可配置后端、知识点过滤、统一 Evidence 映射、向量维度和版本校验，
# 并实现 JSON 与向量存储间的一致性恢复，再把此适配器接入正式 HTTP 链路。
