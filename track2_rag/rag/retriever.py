import json
import os
from pathlib import Path
import chromadb
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi

class HybridRetriever:
    def __init__(self, chunks_path: str, chroma_dir: str):
        with open(chunks_path, "r", encoding="utf-8") as f:
            self.chunks = json.load(f)
        
        # Sparse BM25 setup
        tokenized_corpus = [c["text"].split() for c in self.chunks]
        self.bm25 = BM25Okapi(tokenized_corpus)
        
        # Dense Embeddings & ChromaDB setup
        print("Loading BAAI/bge-m3 embedding model...")
        self.model = SentenceTransformer("BAAI/bge-m3")
        
        Path(chroma_dir).mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=chroma_dir)
        self.collection = self.client.get_or_create_collection(name="statutory_rules")
        
        if self.collection.count() == 0:
            print("Embedding chunks into ChromaDB (this may take a minute)...")
            ids = [c["chunk_id"] for c in self.chunks]
            texts = [c["text"] for c in self.chunks]
            embeddings = self.model.encode(texts, show_progress_bar=True).tolist()
            metadatas = [{"doc": c["doc"], "page": c["page"]} for c in self.chunks]
            self.collection.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
            print("ChromaDB population complete!")
        else:
            print(f"Loaded existing ChromaDB collection with {self.collection.count()} items.")

    def retrieve(self, query: str, k: int = 3):
        query_emb = self.model.encode([query]).tolist()
        results = self.collection.query(query_embeddings=query_emb, n_results=k)
        retrieved = []
        for i in range(len(results["ids"][0])):
            retrieved.append({
                "chunk_id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i]
            })
        return retrieved

if __name__ == "__main__":
    retriever = HybridRetriever("track2_rag/corpus/chunks.json", "track2_rag/chroma_db")
    test_query = "Wetland Buffer Area development assessment requirements"
    print(f"\nRunning test query: '{test_query}'")
    matches = retriever.retrieve(test_query, k=2)
    for m in matches:
        print(f"\n[Match: {m['chunk_id']}] (Doc: {m['metadata']['doc']}, Page: {m['metadata']['page']})")
        print(m['text'][:200] + "...")