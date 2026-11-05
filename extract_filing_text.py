# Extracting filing text
from bs4 import BeautifulSoup
from pathlib import Path

# locate the downloaded filings
filing_folder = Path("data/filings")

# Find the HTML files
html_files = list(filing_folder.glob("*.html"))

if not html_files:
    print("No HTML filings found.")
    raise SystemExit

filing_path = html_files[0]

# read HTML document
with open(filing_path, "r", encoding="utf-8") as file:
    html_content = file.read()

# Extract readable text
soup = BeautifulSoup(html_content, "html.parser")

# Remove unnecessary HTML elements
for element in soup(["script", "style", "ix:header"]):
    element.decompose()

filing_text = soup.get_text(separator=" ", strip=True)

# Create output folder
output_folder = Path("data/processed")
output_folder.mkdir(parents=True, exist_ok=True)

# Save extracted text
text_path = output_folder / "Apple_8K_extracted.txt"

text_path.write_text(filing_text, encoding="utf-8")

print("Text extraction successful!")
print("Source filing:", filing_path)
print("Extracted text saved:", text_path)
print("Number of characters:", len(filing_text))

# preview
print("\nFILING TEXT PREVIEW:\n")
print(filing_text[:2000])



# Display final 2500 characters
print("\nFILING TEXT END:\n")
print(filing_text[-2500:])

# Confirming if code can decipher files for required info
keywords = [
    "Item 1.01",
    "Item 2.02",
    "Item 7.01",
    "Item 8.01",
    "Item 9.01",
    "Exhibit 99"
]

print("\nRELEVANT SECTIONS FOUND:\n")

for keyword in keywords:
    if keyword.lower() in filing_text.lower():
        print(keyword, "FOUND")
    else:
        print(keyword, "NOT FOUND")