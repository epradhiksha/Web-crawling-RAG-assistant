# Responsible for:
# Query processing
# Retrieval
# Prompt construction
# LLM answer generation
# Returning sources

import re
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import (
    SystemMessage,
    HumanMessage
)
import chromadb
from sentence_transformers import SentenceTransformer

load_dotenv()

TOP_K = 5
HISTORY_TURNS = 6 


with open("rag_prompt.txt","r",encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()



llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0)

client = chromadb.PersistentClient(path="vector_store")
collection = client.get_collection(
    name="credit_card_info"
)
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

def validate_query(query):
    query = (query or "").strip()
    if not query:
        return False, "Please enter a question."

    if len(query) < 3:
        return False, "Please enter a more detailed question."
    return True, query

def generate_query_embedding(query):
    embedding = model.encode(query,normalize_embeddings=True)
    return embedding.tolist()

def retrieve_relevant_chunks(query, top_k=TOP_K):
    query_embedding = generate_query_embedding(query)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k
    )

    document= results["documents"][0]
    metadata = results['metadatas'][0]
    distances = results['distances'][0]
    return document, metadata, distances


def answer_query(query, history=None):
    is_valid, query = validate_query(query)
    if not is_valid:
        return query, [], []

    history = (history or [])[-HISTORY_TURNS:]

    # Retrieval always happens before answer generation
    try:
        document, metadata, distances = retrieve_relevant_chunks(query)
    except Exception as e:
        return f"Sorry, the knowledge base could not be searched right now ({type(e).__name__}). Please try again.", [], []

    context = "\n\n".join(
        f"[Source URL: {m['source_url']}]\n{d}" for d, m in zip(document, metadata)
    )
    convo = "\n".join(f"{t['role']}: {t['content']}" for t in history)

    prompt = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Conversation so far:\n{convo}\n\nContext:\n{context}\n\nQuestion: {query}"),
    ]

    try:
        response = llm.invoke(prompt)
    except Exception as e:
        return f"Sorry, the answer could not be generated right now ({type(e).__name__}). Please try again.", [], distances

    answer, used_urls = split_sources(str(response.content))

    # Keep only cited URLs that were actually retrieved, one entry per URL
    sources, seen = [], set()
    for m in metadata:
        url = m["source_url"]
        if url in used_urls and url not in seen:
            seen.add(url)
            sources.append({"card_name": m["card_name"], "source_url": url})
    return answer, sources, distances


def split_sources(text):
    # The prompt makes the model end with a "Sources:" section (URLs or "None")
    head, sep, tail = text.rpartition("Sources:")
    if not sep:
        return text.strip(), set()
    return head.strip(), set(re.findall(r"https?://[^\s)>\]]+", tail))
