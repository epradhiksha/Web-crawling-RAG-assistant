# RAG Strategy

## Crawling Strategy

**Library:** Selenium with Chrome WebDriver. The Bank of America card pages build their product sections with JavaScript, so a real browser is used instead of `requests` + BeautifulSoup.

**Pages crawled:**
1. **Start page:** `https://www.bankofamerica.com/credit-cards/`
2. **Category pages:** links on the start page whose path contains `cards`, such as cash back, travel, airline, student and secured cards.
3. **Card product pages:** the individual card links found on each category page (`/credit-cards/products/...`). The current crawl found **22 cards**.

**Fields extracted from each product page:**

| Field | How it is extracted |
|---|---|
| `card_name` | Text of the link that led to the page |
| `category` | Taken from the URL slug, e.g. `travel-rewards-credit-card` becomes "Travel Rewards" |
| `description` | Element with id `cardDetailsCcModule` |
| `features` | Elements with class `feature-content` |
| `benefits` | Elements with class `benefit-content` |
| `rates_fees` | The `interestRatesFeesCcModule` section |
| `source_url` | The page URL |

**How relevant URLs were identified** (`check()` in `crawler.py`). A link is followed only if all of these hold:
- It points inside `bankofamerica.com/credit-cards`.
- Its text mentions "card" or "credit".
- Its text is not a UI or navigation label such as "Apply now", "Learn more", "Sign in", "Compare", "Contact us", "View all cards" or "Card details".
- Its URL is not a terms and conditions, card agreement, compare tool, or in-page anchor link.

**How duplicate and unrelated pages were filtered:**
- **URL normalization:** URLs are normalized (query string and fragment removed, trailing slash added).
- **One visit per card page:** URLs are tracked in a `seen_urls` set, so each card page is collected only once, even when several category pages link to it.
- **One visit per category page:** category URLs are de-duplicated before they are visited.
- **Empty pages dropped:** pages where no description, features, benefits or rates were extracted are not saved.
- **Polite and fault-tolerant loading:** every page load waits 3 seconds first, and `WebDriverWait` gives each page up to 15 seconds. A page that fails to load is skipped and recorded in `data/crawl_failures.json` instead of stopping the crawl; pages with no card content are recorded there too.
- **Second pass in `preprocess.py`:** records are de-duplicated again by `source_url`, and records with no content are removed.
- **No login pages:** only public pages are visited. No login or account pages are opened, and there is no CAPTCHA or bot-protection workaround.

**Cleaning (`preprocess.py`):**
- Unicode normalization (NFKC).
- Removal of ®, ™, † and the footnote markers.
- Removal of UI text such as "opens in a new window" and "Learn more…" links.
- Removal of offer banners and BofA Rewards promotional text.
- Removal of the rates-table heading, terms link and payment-allocation note.
- Whitespace normalization.
- Case-insensitive removal of duplicate features and benefits within a card.

The cleaned records overwrite `scraped_cards.json`.

## Chunking Strategy

| Setting | Value |
|---|---|
| Splitting method | Section-aware split + LangChain `RecursiveCharacterTextSplitter` |
| Chunk size | 800 characters (~200 tokens) |
| Overlap | 100 characters |
| Separators | newline, sentence end (`. `), space |
| Result | 119 chunks from 22 cards |

**How chunks are built** (`create_chunks()` in `preprocess.py`):
1. Each card is split into three sections:
   - **Features and offers:** the features, plus the description text that isn't already a feature (`clean_record()` removes the repeated features from the description).
   - **Benefits.**
   - **Rates and fees.**
2. Each section is split with the recursive splitter. Features and benefits are joined with newlines, so splits fall between items where possible.
3. Every chunk is prefixed with a header:
   ```
   Card: <card name>
   Category: <category>
   Section: <section>
   ```
4. The chunks are saved to `data/processed_chunks.json`.

**Reasoning:**
- **Sections:** a chunk never mixes fee data with marketing text, so a fee question retrieves the fee table directly.
- **Header:** without it, a chunk like "Annual Fee $0" can't be linked to a card, either by the embedding search or by the LLM. The header also keeps cards with identical standard benefits distinguishable.
- **No repeated description:** the page's description block repeats every feature word for word. Only the leftover text, such as the secured-card eligibility note, is kept, so the same text isn't embedded twice.
- **Smaller than the suggested 500–1,000 tokens:** the embedding model only reads the first 256 word pieces of an input and ignores the rest. 800 characters plus the header (~230 tokens) fits, so the whole chunk is embedded.
- **Overlap:** the 100-character overlap keeps a sentence that crosses a split boundary readable in both chunks.

**Metadata kept on every chunk:** `card_name`, `category`, `section`, `source_url`, `chunk_id`.

## Embedding Model

| | |
|---|---|
| Model | `sentence-transformers/all-MiniLM-L6-v2` |
| Library | `sentence-transformers` |
| Dimensions | 384 |
| Normalization | L2-normalized (`normalize_embeddings=True`) for chunks and queries |

**Reason for selection:**
- It's free and open-source, and runs locally on CPU with no API key.
- It's small (~90 MB) and fast to embed the whole corpus.
- It's a strong general-purpose model for semantic search over short passages, which matches the short, factual card text.
- The same model embeds both the chunks and the user's query, so their vectors are directly comparable.

## Vector Database

| | |
|---|---|
| Database | ChromaDB `PersistentClient` (local) |
| Location | `vector_store/` |
| Collection | `credit_card_info` |
| Distance | cosine (`hnsw:space = cosine`) |

**Reason for selection:**
- **Metadata with every result:** ChromaDB stores each vector with its text and metadata, so every search result already carries its `source_url`, `card_name` and `category`. That's what the source citation needs.
- **No server:** it runs embedded in Python, and the index is a local folder that can be rebuilt with one command.
- **Clean rebuilds:** `index.py` deletes and recreates the collection on every run, so re-indexing never leaves duplicate or stale chunks. It loads the chunks from `data/processed_chunks.json`, and if there are none it stops before deleting the existing index.

## Retrieval Strategy

| | |
|---|---|
| Top-k | 5 |
| Similarity | Cosine similarity between the query embedding and the chunk embeddings |
| LLM | Groq `openai/gpt-oss-120b`, temperature 0 |

**Reasoning for k = 5:**
- **Enough for one card:** a card has 4–7 chunks, so five results cover most of one card's relevant sections. For example, "annual fee of the Premium Rewards card" returns the fee chunks of both Premium Rewards and Premium Rewards Elite.
- **Enough for comparison:** for a broad question, five results cover several different cards. The LLM can then see when a question could mean more than one card and ask which one the user means, instead of guessing.
- **Small prompt:** five chunks of ~230 tokens each keep the prompt short and leave less room for unrelated text.

**Query flow (`rag_api.py`):**
1. **Validate:** empty, whitespace-only and very short (fewer than 3 characters) queries are rejected.
2. **Retrieve:** the user's question is embedded as typed and the top 5 chunks are retrieved. Retrieval always happens before generation.
3. **Build the prompt:** the system prompt from `rag_prompt.txt`, the last 6 chat messages, and the retrieved chunks, each labelled with its source URL.
4. **Generate:** the LLM answers in the required `Answer:` / `Sources:` format.
5. **Check sources:**
   - A URL is shown only if the LLM cited it **and** it belongs to a retrieved chunk.
   - Fallback, clarification and off-topic answers cite `None`, so no links are shown for them.
