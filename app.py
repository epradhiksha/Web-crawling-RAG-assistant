# Responsible for:
# Gradio or Streamlit UI
# Taking user questions
# Displaying answers and sources

import json
import os
import streamlit as st
from rag_api import answer_query

# session_state is wiped on browser refresh, so the chat is also kept on disk
HISTORY_FILE = "chat_history.json"


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def show_sources(sources):
    if not sources:
        return
    st.markdown("### Sources")
    for source in sources:
        st.markdown(f"- [{source['card_name']}]({source['source_url']})")


st.title("Bank of America Credit Card Assistant")
if st.button("Clear"):
    st.session_state.history = []
    save_history([])
    st.rerun()
if "history" not in st.session_state:
    st.session_state.history = load_history()

for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        show_sources(msg.get("sources"))

text = st.chat_input("Ask anything")
if text:
    with st.chat_message("user"):
        st.markdown(text)

    # Send question + previous conversation to RAG
    answer, sources, distances = answer_query(text, st.session_state.history)

    # Display answer, with sources only if the model actually used any
    with st.chat_message("assistant"):
        st.markdown(answer)
        show_sources(sources)

    st.session_state.history.extend([
        {"role": "user", "content": text},
        {"role": "assistant", "content": answer, "sources": sources},
    ])
    save_history(st.session_state.history)
