
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd
from ollama import chat

# ******************************************************
# 1. Project configuration
# ******************************************************

PROJECT_FOLDER = Path(__file__).resolve().parent
OUTPUT_FOLDER = PROJECT_FOLDER / "output"

OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

MODEL = "llama3.2:latest"
CHUNK_SIZE = 2000 # reduced due to computing restrictions
OVERLAP = 200

# Pilot: one exhibit from each company
PILOT_DOCUMENTS = {
    ("AAPL", "0000320193-26-000024"),
    ("NVDA", "0001045810-26-000073"),
    ("MSFT", "0001193125-26-436122")
}

GENERIC_PRODUCT_NAMES = {
    "iphone", "ipad", "mac", "macbook",
    "apple watch", "airpods", "windows",
    "azure", "surface", "geforce", "rtx",
    "kindle", "echo", "alexa", "pixel",
    "chromebook"
}

# ******************************************************
# 2. Helper fx
# ******************************************************

def normalize_text(text):
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("‘", "'").replace("’", "'")
    text = re.sub(r"\s+", " ", text)
    return text.strip(' "\'“”‘’')


def split_text(text, chunk_size=3500, overlap=400):
    if overlap >= chunk_size:
        raise ValueError("Overlap must be smaller than chunk size.")

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        if end < len(text):
            boundary = text.rfind(
                ". ",
                start + chunk_size // 2,
                end
            )
            if boundary != -1:
                end = boundary + 1

        chunks.append(text[start:end])

        if end == len(text):
            break

        start = max(start + 1, end - overlap)

    return chunks


def extract_products(chunk):
    prompt = f"""
You are an expert information extraction system analyzing
SEC Form 8-K filings and exhibits.

Identify specifically named products that the company
explicitly announces, introduces, launches, or releases
as "NEW".

RULES:
1. Extract only specifically named new products.
2. Do not extract existing products mentioned for context.
3. Do not extract broad product families.
4. Do not extract features unless explicitly announced
   as standalone products.
5. Do not infer that a product is new from its name.
6. Financial results are not product announcements.
7. Provide a short exact supporting quotation.
8. Keep descriptions under 180 characters.
9. If evidence is insufficient, return no products.

Return ONLY JSON:

{{
    "products": [
        {{
            "new_product": "Specific product name",
            "product_description": "Brief description",
            "evidence": "Exact quotation from the excerpt"
        }}
    ]
}}

If no qualifying products exist, return:
{{"products": []}}

DOCUMENT EXCERPT:
{chunk}
"""

    response = chat(
        model=MODEL,
        messages=[
            {"role": "user", "content": prompt}
        ],
        format="json",
        options={
            "temperature": 0,
            "num_ctx": 4096,
            "num_predict": 512 # reduced due to computing restrictions
        }
    )

    return json.loads(response.message.content)


# ******************************************************
# 3. Read exhibit inventory
# ******************************************************


# Read all extracted main filings
filings = pd.read_csv(
    OUTPUT_FOLDER / "processed_filing_inventory.csv",
    dtype={"accession": str}
)

# Read all extracted exhibits
exhibits = pd.read_csv(
    OUTPUT_FOLDER / "exhibit_inventory.csv",
    dtype={"accession": str}
)

# Standardize columns needed for extraction
columns = [
    "company_name",
    "stock_name",
    "accession",
    "filing_time",
    "text_path"
]

filings = filings[columns].copy()
exhibits = exhibits[columns].copy()

# Combine the two document inventories
documents = pd.concat(
    [filings, exhibits],
    ignore_index=True
)

# Remove duplicate file paths, if any
documents = documents.drop_duplicates(
    subset=["text_path"]
)

print("Main filings:", len(filings))
print("Exhibits:", len(exhibits))
print("Total documents selected:", len(documents))


# ******************************************************
# 4. Process documents
# ******************************************************

results_path = OUTPUT_FOLDER / "all_product_candidates.json"
status_path = OUTPUT_FOLDER / "all_processing_status.json"


# Load previously saved candidates and processing status
if results_path.exists():
    with open(results_path, "r", encoding="utf-8") as file:
        saved_results = json.load(file)

    all_candidates = saved_results.get("products", [])
else:
    all_candidates = []

if status_path.exists():
    with open(status_path, "r", encoding="utf-8") as file:
        processing_status = json.load(file)
else:
    processing_status = []

# Identify documents that completed successfully
completed_documents = {
    Path(str(item["source_document"])).name
    for item in processing_status
    if item.get("status") == "complete"
    and item.get("source_document")
}

print("Previously completed documents:", len(completed_documents))




for _, document in documents.iterrows():

    ticker = document["stock_name"]
    accession = document["accession"]
    text_path = Path(document["text_path"])

    if not text_path.is_absolute():
        text_path = PROJECT_FOLDER / text_path

    document_key = text_path.name

    if document_key in completed_documents:
        print(f"Skipping completed document: {document_key}")
        continue

    # Only documents NOT previously completed reach this line
    print(f"\nProcessing {ticker}: {text_path.name}")

    if not text_path.is_file():
        print("Missing document:", text_path)

        processing_status.append({
            "ticker": ticker,
            "accession": accession,
            "source_document": text_path.name,
            "status": "missing_file"
        })
        continue

    document_text = text_path.read_text(encoding="utf-8")

    chunks = split_text(
        document_text,
        CHUNK_SIZE,
        OVERLAP
    )

    print("Total chunks:", len(chunks))

    completed_chunks = 0
    failed_chunks = 0

    for chunk_number, chunk in enumerate(chunks, start=1):

        print(f"Analyzing chunk {chunk_number}/{len(chunks)}")

        try:
            result = extract_products(chunk)

            products = result.get("products", [])

            if not isinstance(products, list):
                raise ValueError("Invalid products list")

            completed_chunks += 1

        except Exception as error:
            print("Chunk failed:", error)
            failed_chunks += 1
            continue

        for product in products:

            if not isinstance(product, dict):
                continue

            name = product.get("new_product")
            description = product.get("product_description")
            evidence = product.get("evidence")

            if not all(
                isinstance(value, str)
                for value in (name, description, evidence)
            ):
                continue

            name = name.strip()
            description = description.strip()
            evidence = evidence.strip()

            if not name or not description or not evidence:
                continue

            if name.casefold() in GENERIC_PRODUCT_NAMES:
                continue

            if len(description) >= 180:
                continue

            if normalize_text(evidence) not in normalize_text(chunk):
                print("Rejected unsupported evidence:", name)
                continue

            all_candidates.append({
                "company_name": document["company_name"],
                "stock_name": ticker,
                "accession": accession,
                "filing_time": document["filing_time"],
                "source_document": text_path.name,
                "chunk_number": chunk_number,
                "new_product": name,
                "product_description": description,
                "evidence": evidence,
                "review_status": "unverified"
            })

    processing_status.append({
        "ticker": ticker,
        "accession": accession,
        "source_document": text_path.name,
        "total_chunks": len(chunks),
        "completed_chunks": completed_chunks,
        "failed_chunks": failed_chunks,
        "status": (
            "complete" if failed_chunks == 0
            else "incomplete"
        )
    })

    # Saving progress after each document
    results_path.write_text(
        json.dumps(
            {"products": all_candidates},
            indent=4,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    status_path.write_text(
        json.dumps(
            processing_status,
            indent=4
        ),
        encoding="utf-8"
    )

    print(
        f"Finished {ticker}: "
        f"{completed_chunks}/{len(chunks)} chunks completed"
    )

# ******************************************************
# 5. Summary
# ******************************************************

print("\nFULL EXTRACTION COMPLETE")
print("Documents processed:", len(processing_status))
print("Candidates extracted:", len(all_candidates))

print("\nPRODUCT CANDIDATES:")

for product in all_candidates:
    print(
        product["stock_name"],
        "-",
        product["new_product"]
    )

print("\nResults saved:", results_path.resolve())
print("Status saved:", status_path.resolve())

# :)