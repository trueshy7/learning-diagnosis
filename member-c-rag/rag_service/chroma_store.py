"""不可变代际集合，目录切换前完成构建；JSON 目录是唯一活动清单。"""
import hashlib
from functools import cached_property

from .embeddings import Embeddings


class ChromaStore:
    def __init__(self, settings):
        self.settings = settings
        self.embeddings = Embeddings(settings)
        self.cache = {}

    @cached_property
    def client(self):
        import chromadb
        from chromadb.config import Settings
        return chromadb.PersistentClient(path=str(self.settings.chroma_path),
                                        settings=Settings(anonymized_telemetry=False))

    def name(self, data):
        return "rag_" + hashlib.sha256((data["index_version"] + self.embeddings.signature).encode()).hexdigest()[:32]

    def build(self, data):
        name = self.name(data)
        chunks = [(doc, chunk) for doc in data["documents"].values() for chunk in doc["chunks"]]
        collection = self.client.get_or_create_collection(
            name, embedding_function=None, configuration={"hnsw": {"space": "cosine"}},
            metadata={"signature": self.embeddings.signature, "ready": False})
        if collection.metadata.get("ready") and collection.count() == len(chunks):
            return collection
        for start in range(0, len(chunks), self.settings.batch_size):
            batch = chunks[start:start + self.settings.batch_size]
            missing = [chunk["text"] for _, chunk in batch if chunk["content_hash"] not in self.cache]
            if missing:
                for text, vector in zip(missing, self.embeddings.embed(missing)):
                    self.cache[hashlib.sha256(text.encode()).hexdigest()] = vector
            collection.upsert(ids=[chunk["chunk_id"] for _, chunk in batch],
                              documents=[chunk["text"] for _, chunk in batch],
                              embeddings=[self.cache[chunk["content_hash"]] for _, chunk in batch],
                              metadatas=[{"course_id": doc["course_id"], "resource_id": doc["resource_id"],
                                          "document_id": doc["document_id"], "resource_version": doc["resource_version"]}
                                         for doc, _ in batch])
        if collection.count() != len(chunks):
            raise ValueError("向量集合片段数不匹配")
        collection.modify(metadata={"signature": self.embeddings.signature, "ready": True})
        return collection

    def rank(self, data, query, eligible_chunks, top_k):
        if not eligible_chunks:
            return []
        collection = self.build(data)  # 派生库遗失可由目录重建。
        vector = self.embeddings.embed([query], query=True)[0]
        # 在 ANN 排序前限制到已验证课程/标签/版本范围的片段 ID。
        results = collection.query(query_embeddings=[vector], ids=list(eligible_chunks),
                                   n_results=min(top_k, len(eligible_chunks)), include=["distances"])
        return [(cid, 1. - float(distance)) for cid, distance in zip(results["ids"][0], results["distances"][0])]

    def cleanup(self, data):
        keep = self.name(data)
        for item in self.client.list_collections():
            name = item.name if hasattr(item, "name") else item
            if name.startswith("rag_") and name != keep:
                self.client.delete_collection(name)
