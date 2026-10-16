# Responsible for:
# Loading processed chunks
# Generating embeddings
# Building/storing the vector index


import json

import chromadb
from sentence_transformers import SentenceTransformer

CHUNKS_INPUT = "data/processed_chunks.json"
VECTOR_STORE_PATH = "vector_store"
COLLECTION_NAME = "credit_card_info"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def load_chunks():
    # Chunks are created by preprocess.py
    with open(CHUNKS_INPUT, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    valid = []
    for chunk in chunks:
        # Never embed empty text or chunks that lost their source
        if not chunk.get("text", "").strip() or not chunk.get("source_url"):
            continue
        valid.append(chunk)
    print(f"Loaded {len(valid)} chunks from {CHUNKS_INPUT}")
    return valid


def build_index(chunks):
    client = chromadb.PersistentClient(path=VECTOR_STORE_PATH)

    # Rebuild from scratch so re-running never leaves stale or duplicate chunks
    if COLLECTION_NAME in [c.name for c in client.list_collections()]:
        client.delete_collection(COLLECTION_NAME)
    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    model = SentenceTransformer(EMBEDDING_MODEL)
    documents = [c["text"] for c in chunks]
    embeddings = model.encode(documents, normalize_embeddings=True)

    collection.add(
        ids=[c["id"] for c in chunks],
        documents=documents,
        embeddings=embeddings.tolist(),
        metadatas=[
            {
                "card_name": c["card_name"],
                "category": c["category"],
                "section": c["section"],
                "source_url": c["source_url"],
                "chunk_id": c["chunk_id"],
            }
            for c in chunks
        ],
    )
    return collection


if __name__ == "__main__":
    chunks = load_chunks()
    collection = build_index(chunks)
    print("Total documents in collection:", collection.count())
