# Responsible for:
# Cleaning scraped content
# Removing duplicates/noise
# Chunking text
# Preserving metadata



import json
import os
import re
import unicodedata

from langchain_text_splitters import RecursiveCharacterTextSplitter

INPUT_FILE = "scraped_cards.json"
CHUNKS_OUTPUT = "data/processed_chunks.json"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100


NOISE = [
    r"Footnote\s*\[\s*\d+\s*\]",

    # Navigation / UI text
    r"Learn more at the Security Center",
    r"(?i)opens in a new window",
    r"(?i)current page",
    r"(?i)^Card Details\s*",

    # Learn-more UI links
    r"(?i)Learn more about Digital Wallets Technology",
    r"(?i)Learn more about Customized Cash Rewards",
    r"(?i)Learn more cash back categories",
    r"(?i)Learn more about credit",

    # BofA promotional boilerplate
    r"(?i)Achieve more with BofA Rewards(?:TM|SM)?",
    r"(?i)Enrich your experience as a Bank of America customer with the BofA Rewards(?:TM|SM)? program.*?enrollment\.",

    # Offer / banner UI
    r"(?i)This offer may not be available elsewhere if you leave this page\.",
    r"(?i)This offer may not be available if you leave this page\.",
    r"(?i)You can take advantage of this offer when you apply now\.",

    # Trademark symbols
    r"™",
]


RATES_NOISE = [

    # Section heading
    r"(?i)^Interest Rates & Fees Summary\s*",

    # Terms and conditions UI text
    r"(?i)Please see Terms and Conditions\*?\s*"
    r"for rate, fee and other cost information.*?"
    r"payment allocation\.",

    # Additional payment explanation / UI text
    r"(?i)Note:\s*minimum payments are applied to lower-interest balances first\.\s*"
    r"Additional payments are applied to higher-interest balances first\.",

    # Navigation
    r"(?i)View complete list of rates and fees",
]


def preprocess(text):
    if text is None:
        return ""

    # Make sure the value is a string
    text = str(text)

    # Normalize Unicode characters
    text = unicodedata.normalize("NFKC", text)
    text = (
        text
        .replace("®", "")
        .replace("†", "")
        .replace("ﬅ", "ft")
        .replace("™", "")
        .replace("�", "-")          
        .replace("RewardsSM", "Rewards")
    )
    # Trademark marks glued onto words (AtmosTM, ONETM, PayTM), but keep "ATM"
    text = re.sub(r"\b(?!ATM\b)(\w+?)TM\b", r"\1", text)
    # Remove known noise patterns
    for pattern in NOISE:
        text = re.sub(pattern, "", text)
    # Remove rates/fees-specific noise
    for pattern in RATES_NOISE:
        text = re.sub(pattern, "", text)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def unique_items(items):
    seen = set()
    cleaned = []

    for item in items:

        item = item.strip()

        if not item:
            continue

        # Case-insensitive duplicate check
        key = item.casefold()

        if key in seen:
            continue

        seen.add(key)
        cleaned.append(item)
    return cleaned


def clean_record(rec):
    rec["card_name"] = preprocess(rec["card_name"])
    rec["category"] = preprocess(rec.get("category", ""))
    rec["source_url"] = rec.get("source_url", "").strip()
    rec["features"] = unique_items([preprocess(t) for t in rec.get("features", [])])
    rec["benefits"] = unique_items([preprocess(t) for t in rec.get("benefits", [])])
    rec["rates_fees"] = preprocess(rec.get("rates_fees"))

    # The page's description block repeats every feature; keep only the extra text
    # (e.g. secured-card eligibility notes) so features are not stored twice.
    description = preprocess(rec.get("description"))
    for feature in rec["features"]:
        description = description.replace(feature, " ")
    rec["description"] = re.sub(r"\s+", " ", description).strip()
    return rec


def clean_records(raw):
    cleaned, seen_urls, seen_content = [], set(), set()
    for rec in raw:
        rec = clean_record(rec)
        if not rec["source_url"] or rec["source_url"] in seen_urls:
            continue
        if not (rec["description"] or rec["features"] or rec["benefits"] or rec["rates_fees"]):
            continue

        # Same page reached through a different URL
        content_key = (rec["card_name"].casefold(), " ".join(rec["features"]), rec["rates_fees"])
        if content_key in seen_content:
            continue

        seen_urls.add(rec["source_url"])
        seen_content.add(content_key)
        cleaned.append(rec)
    return cleaned


def create_chunks(records):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n", ". ", " ", ""],
    )

    chunks = []
    for rec in records:
        sections = {
            "Features and offers": "\n".join(
                ([rec["description"]] if rec["description"] else []) + rec["features"]
            ),
            "Benefits": "\n".join(rec["benefits"]),
            "Rates and fees": rec["rates_fees"],
        }
        slug = rec["source_url"].rstrip("/").split("/")[-1]

        chunk_id = 0
        for section, body in sections.items():
            if not body.strip():
                continue
            for piece in splitter.split_text(body):
                piece = piece.strip()
                if not piece:
                    continue
                chunk_id += 1
                # The header makes every chunk self-describing for retrieval and for the LLM
                header = f"Card: {rec['card_name']}\nCategory: {rec['category']}\nSection: {section}\n"
                chunks.append({
                    "id": f"{slug}-{chunk_id}",
                    "text": header + piece,
                    "card_name": rec["card_name"],
                    "category": rec["category"],
                    "section": section,
                    "source_url": rec["source_url"],
                    "chunk_id": chunk_id,
                })
    return chunks


def run():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)

    cleaned = clean_records(raw)

    # Clean the same file in place
    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=2, ensure_ascii=False)
    print(f"Read {len(raw)} records, saved {len(cleaned)} cleaned cards to {INPUT_FILE}")

    # Chunks with metadata are what index.py embeds
    chunks = create_chunks(cleaned)
    os.makedirs(os.path.dirname(CHUNKS_OUTPUT), exist_ok=True)
    with open(CHUNKS_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(chunks)} chunks to {CHUNKS_OUTPUT}")

if __name__ == "__main__":
    run()
