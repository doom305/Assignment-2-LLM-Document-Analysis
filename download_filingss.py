
import requests
import json
from pathlib import Path

PROJECT_FOLDER = Path(__file__).resolve().parent

FILING_FOLDER = PROJECT_FOLDER / "data" / "filings"
FILING_FOLDER.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "SEC Product Research Daniel Dumas da981044@ucf.edu"
}

cik = "0000320193"
ticker = "AAPL"

# Retrieve SEC files
url = f"https://data.sec.gov/submissions/CIK{cik}.json"

response = requests.get(url, headers=HEADERS, timeout=30)
response.raise_for_status()

data = response.json()
recent = data["filings"]["recent"]

# locating most recent 8K files
filing_index = recent["form"].index("8-K")

accession = recent["accessionNumber"][filing_index]
primary_document = recent["primaryDocument"][filing_index]
filing_date = recent["filingDate"][filing_index]
filing_time = recent["acceptanceDateTime"][filing_index]

accession_folder = accession.replace("-", "")

filing_directory = (
    f"https://www.sec.gov/Archives/edgar/data/"
    f"{int(cik)}/{accession_folder}/"
)

filing_url = filing_directory + primary_document

# download the filing
filing_response = requests.get(
    filing_url,
    headers=HEADERS,
    timeout=30
)

filing_response.raise_for_status()

html_path = FILING_FOLDER / f"Apple_8K_{filing_date}.html"
html_path.write_bytes(filing_response.content)

# save metadata for the future scripts
metadata = {
    "company_name": data["name"],
    "stock_name": ticker,
    "cik": cik,
    "accession": accession,
    "filing_date": filing_date,
    "filing_time": filing_time,
    "filing_url": filing_url,
    "filing_directory": filing_directory,
    "html_path": str(html_path)
}

metadata_path = FILING_FOLDER / "apple_filing_metadata.json"

metadata_path.write_text(
    json.dumps(metadata, indent=4),
    encoding="utf-8"
)

print("Filing downloaded successfully!")
print("Company:", data["name"])
print("Filing date:", filing_date)
print("Filing timestamp:", filing_time)
print("Saved filing:", html_path)
print("Saved metadata:", metadata_path)
