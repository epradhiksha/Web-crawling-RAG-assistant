# Assignment 3 – Web Crawling RAG: Bank of America Credit Card Assistant

## Project Overview

This project crawls the public Bank of America credit card pages, cleans the content and indexes it in a vector database. A Retrieval-Augmented Generation (RAG) chatbot then answers questions about the cards using **only** the crawled content, and shows the source pages for every grounded answer.

## Architecture / RAG Flow

```
Bank of America Credit Card Website
            ↓  crawler.py     (Selenium, 3 s delay per page, failed pages recorded)
   scraped_cards.json  +  data/crawl_failures.json
            ↓  preprocess.py  (clean in place, deduplicate, section-aware chunking)
   scraped_cards.json (cleaned)  +  data/processed_chunks.json
            ↓  index.py       (all-MiniLM-L6-v2 embeddings)
   vector_store/  (ChromaDB, cosine similarity)
            ↓
User question → validate → embed → top-5 semantic search
            ↓  rag_api.py
RAG prompt (rag_prompt.txt + recent chat + retrieved chunks) → Groq LLM
            ↓
Grounded answer + verified source URLs → app.py (Streamlit UI)
```

## Technologies Used

| Purpose | Technology |
|---|---|
| Crawling / scraping | Selenium + Chrome WebDriver |
| Chunking | LangChain `RecursiveCharacterTextSplitter` |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` |
| Vector database | ChromaDB (local, persistent) |
| LLM | Groq API, `openai/gpt-oss-120b`, via `langchain-groq` |
| UI | Streamlit |

## Project Structure

```
├── crawler.py               # Crawl start page → category pages → card product pages
├── preprocess.py            # Clean, deduplicate, chunk and keep metadata
├── index.py                 # Load chunks, embed them, build the ChromaDB index
├── rag_api.py               # Validation, retrieval, prompt building, LLM call, sources
├── app.py                   # Streamlit chat UI
├── rag_prompt.txt           # System prompt (role, purpose, grounding, sources, fallback, ambiguity, format)
├── rag_strategy.md          # Crawling / chunking / embedding / vector DB / retrieval decisions
├── test_log.md              # Actual outputs for the required test scenarios
├── scraped_cards.json       # Crawled card records, cleaned in place by preprocess.py
├── requirements.txt
├── .env.example
├── data/
│   ├── processed_chunks.json  # Chunks with metadata (created by preprocess.py)
└── vector_store/              # ChromaDB index (created by index.py)
```

## Installation

You need **Python 3.10+** and **Google Chrome**. Selenium 4 downloads the matching ChromeDriver automatically.

```bash
python -m venv venv
venv\Scripts\activate            # Windows
pip install -r requirements.txt
```


## Configure the LLM

1. Create a free API key at https://console.groq.com/keys.
2. Copy `.env.example` to `.env` and add your key:
   ```
   GROQ_API_KEY=your_groq_api_key_here
   ```

## Running the Project

Run each step from the project folder, in this order.

### 1. Run the crawler
```bash
python crawler.py
```

### 2. Preprocess the data
```bash
python preprocess.py
```

### 3. Build the vector index
```bash
python index.py
```


### 4. Start the Streamlit app
```bash
streamlit run app.py --server.fileWatcherType none
```


## Example Queries

| Type | Example | Expected behaviour |
|---|---|---|
| Product information | "What rewards does the Customized Cash Rewards card offer?" | Grounded answer + source URL |
| Rates / fees | "What is the annual fee for the Premium Rewards Elite card?" | $550 + source URL |
| Not available | "What is the late payment fee for the Travel Rewards card?" | "I could not find this information…", no sources |
| Ambiguous | "What is the annual fee?" | Asks which card you mean |
| Off-topic | "What is the capital of France?" | Polite refusal, no sources |

## Assumptions and Known Limitations

- **The content is a snapshot.** It reflects the website on the day the crawler was run. Re-run steps 1–3 to refresh it.
- **The crawler depends on the current page layout.** It reads specific HTML IDs and classes (`cardDetailsCcModule`, `feature-content`, `benefit-content` and the rates and fees module). If Bank of America changes its pages, those selectors need updating.
- **Some fields aren't separate.** Welcome offers, rewards, eligibility notes and important terms are captured inside `features`, `description` and `rates_fees`, because that's how the product pages present them. A field missing from a page is left empty, never invented.
- **Categories come from each card's URL** (for example "Alaska Airlines", "Travel Rewards"), not from the site's broader groups such as "Airline Rewards".
- **Only the summary rates table is indexed.** The full Terms & Conditions and card agreements are excluded, so details like late or cash advance fees aren't available.
- **Follow-up questions aren't rewritten before searching.** A follow-up that doesn't name the card (for example "what is its APR?") may not find the right card, and the assistant will then ask which card you mean. Naming the card always works.
- **Chat history is shared.** It's saved to a single local `chat_history.json`, so it survives a page refresh, but everyone using the same running app shares it.
- **Answers depend on retrieval.** An answer is only as complete as the top 5 retrieved chunks. The prompt rules and source checks reduce hallucination, but can't guarantee against it completely.
