"""
auto_mapper.py
--------------
Two jobs:
1. AUTO-DETECT which pages of a 10-K PDF contain the income statement
   and balance sheet (so you never have to find page numbers manually).

2. AUTO-GENERATE the metric mapping JSON using the local LLM (Mistral).
   When a new company PDF arrives, this reads the raw labels from the PDF,
   asks the LLM to map them to standard keys, and saves the result to
   configs/metric_mappings/{company}.json automatically.
"""

import re
import json
from pathlib import Path
from collections import defaultdict

import fitz       # PyMuPDF
import ollama

from src.schemas.financial_schema import STANDARD_SCHEMA


# Absolute path to configs/ — anchored to this file's location.
# Path(__file__) = .../src/auto_mapper.py
# .parent        = .../src/
# .parent.parent = .../GraphRAG/   (project root)
# This means the path is ALWAYS correct regardless of which directory
# the notebook or script is running from.
CONFIGS_DIR = Path(__file__).parent.parent / "configs" / "metric_mappings"


# ---------------------------------------------------------------------------
# Keywords that appear at the top of financial statement pages
# ---------------------------------------------------------------------------

INCOME_KEYWORDS = [
    "CONSOLIDATED STATEMENTS OF INCOME",
    "CONSOLIDATED STATEMENTS OF OPERATIONS",
    "CONSOLIDATED INCOME STATEMENTS",
    "INCOME STATEMENTS",
    "STATEMENTS OF INCOME",
    "STATEMENTS OF OPERATIONS",
]

BALANCE_KEYWORDS = [
    "CONSOLIDATED BALANCE SHEETS",
    "CONSOLIDATED BALANCE SHEET",
    "BALANCE SHEETS",
    "BALANCE SHEET",
]


# ---------------------------------------------------------------------------
# Step A: Auto-detect financial statement page numbers
# ---------------------------------------------------------------------------

def detect_financial_pages(pdf_path: str) -> dict:
    """
    Scan the PDF and return which pages contain the income statement
    and balance sheet, based on keyword matching.

    TWO-PART FILTER (prevents false positives from TOC and notes pages):
    1. Keyword must appear in first 250 chars — it must be the PAGE TITLE,
       not a reference buried in footnotes or notes sections.
    2. Page must contain actual financial numbers (comma-formatted like 26,974)
       — this eliminates Table of Contents listing pages which only show
       statement names and page numbers but no financial data.

    Returns
    -------
    dict with keys:
        "income_statement" -> list of page numbers (1-indexed)
        "balance_sheet"    -> list of page numbers (1-indexed)
    """
    doc = fitz.open(pdf_path)
    result = {"income_statement": [], "balance_sheet": []}

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        text = page.get_text()

        # Filter 1: keyword must be in the first 250 chars (= page title area)
        # This means the financial statement name is the HEADING of this page,
        # not just referenced somewhere inside a note or TOC listing.
        text_top = text[:250].upper()

        # Filter 2: page must contain actual financial numbers
        # TOC pages list statement names + page numbers but no dollar amounts.
        # Real financial statement pages always have comma-formatted numbers.
        has_numbers = bool(FINANCIAL_NUMBER_PATTERN.search(text))

        if not has_numbers:
            continue

        if any(kw in text_top for kw in INCOME_KEYWORDS):
            result["income_statement"].append(page_idx + 1)

        if any(kw in text_top for kw in BALANCE_KEYWORDS):
            result["balance_sheet"].append(page_idx + 1)

    doc.close()
    return result


def get_target_pages(pdf_path: str) -> list:
    """
    Return the combined list of income statement + balance sheet pages.
    This is what you pass to process_company(target_pages=...).

    If nothing is detected, returns None (pipeline will scan all pages).
    """
    detected = detect_financial_pages(pdf_path)

    income_pages  = detected["income_statement"]
    balance_pages = detected["balance_sheet"]

    print(f"  Auto-detected income statement pages : {income_pages}")
    print(f"  Auto-detected balance sheet pages    : {balance_pages}")

    all_pages = sorted(set(income_pages + balance_pages))

    if not all_pages:
        print("[WARNING] Could not auto-detect financial pages.")
        print("          Will scan all pages (slower, more noise).")
        return None

    print(f"  Combined target pages: {all_pages}")
    return all_pages


# ---------------------------------------------------------------------------
# Step B: Extract raw labels from PDF pages
# ---------------------------------------------------------------------------

FINANCIAL_NUMBER_PATTERN = re.compile(r'\d{1,3}(?:,\d{3})+|\d{4,}')


def extract_raw_labels(pdf_path: str, target_pages: list) -> list:
    """
    Read the target pages and collect all unique text labels that appear
    alongside financial numbers.

    These are the raw strings like:
      "Total revenue", "Income from operations", "Cash and cash equivalents"

    We send this list to the LLM in the next step to auto-generate the mapping.
    """
    doc = fitz.open(pdf_path)
    labels = set()

    for page_idx in range(len(doc)):
        page_num = page_idx + 1
        if target_pages and page_num not in target_pages:
            continue

        page = doc[page_idx]
        words = page.get_text("words")

        if not words:
            continue

        # Group words by Y position (same technique as extractor.py)
        y_buckets = defaultdict(list)
        for word_data in words:
            x0, y0, x1, y1, word_text = word_data[:5]
            y_key = round(y0 / 8) * 8
            y_buckets[y_key].append((x0, word_text))

        for y_key in sorted(y_buckets.keys()):
            words_in_row = sorted(y_buckets[y_key], key=lambda t: t[0])
            line = " ".join(w for _, w in words_in_row).strip()

            # Must start with a letter and contain a large number
            if not line or not line[0].isalpha():
                continue
            if not FINANCIAL_NUMBER_PATTERN.search(line):
                continue

            # Extract just the text label (before the first number)
            match = re.match(r'^([A-Za-z][A-Za-z\s,&/\-–()\'.]+)', line)
            if match:
                label = match.group(1).strip().rstrip(".,: ")
                if len(label) >= 3:
                    labels.add(label)

    doc.close()
    return sorted(labels)


# ---------------------------------------------------------------------------
# Step C: LLM auto-generates the mapping
# ---------------------------------------------------------------------------

def auto_generate_mapping(company_name: str, raw_labels: list) -> dict:
    """
    Send raw PDF labels to the local Mistral LLM and ask it to map
    each one to a standard canonical key.

    Returns a dict like:
        {"total revenue": "total_revenue", "gross profit": "gross_profit", ...}
    """
    standard_keys = list(STANDARD_SCHEMA.keys())

    prompt = f"""You are a financial data engineer building a standardized database.

I extracted these label texts from a company 10-K annual report PDF:
{json.dumps(raw_labels, indent=2)}

Map each label to exactly one of these standard keys (or skip if none fits clearly):
{json.dumps(standard_keys, indent=2)}

What each standard key means:
- total_revenue: top-line revenue, net sales, total revenue
- gross_profit: gross profit or gross margin (revenue minus cost of goods)
- operating_income: operating income, income from operations, operating profit
- net_income: net income, net earnings, profit after tax
- research_and_development: R&D expense, research and development costs
- selling_general_administrative: SG&A, selling general and administrative
- total_operating_expenses: total operating costs / total opex
- total_assets: total assets on the balance sheet
- total_liabilities: total liabilities on the balance sheet
- cash_and_equivalents: cash and cash equivalents

Rules:
1. Output ONLY a valid JSON object. No explanation, no extra text.
2. JSON keys = raw labels from the list above, converted to LOWERCASE only.
   KEEP ALL SPACES. Do NOT replace spaces with underscores.
   Example: "Total revenues" becomes "total revenues" NOT "total_revenues".
   Example: "Cash and cash equivalents" becomes "cash and cash equivalents" NOT "cash_and_cash_equivalents".
3. JSON values = standard keys from the list above (these DO use underscores).
4. Only include mappings you are confident about. Skip unclear ones.

Example of correct output format:
{{
  "total revenues": "total_revenue",
  "gross profit": "gross_profit",
  "cash and cash equivalents": "cash_and_equivalents"
}}

Output:"""

    print(f"  Asking LLM to map {len(raw_labels)} labels...")

    response = ollama.chat(
        model="mistral",
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.0},   # 0 = most deterministic
    )

    content = response["message"]["content"].strip()

    # LLM sometimes adds text before/after JSON — extract just the JSON block
    json_match = re.search(r'\{.*\}', content, re.DOTALL)
    if not json_match:
        print("[WARNING] LLM did not return valid JSON. Mapping will be empty.")
        return {}

    try:
        raw_mapping = json.loads(json_match.group())

        # Validate: only keep entries where the value is a known standard key.
        # Also normalize key format: replace underscores with spaces.
        # Why: Mistral sometimes returns "cash_and_cash_equivalents" instead of
        # "cash and cash equivalents". Since metric_builder.py matches on the
        # raw label text (which uses spaces), we must normalize here.
        valid_mapping = {
            k.lower().replace("_", " "): v
            for k, v in raw_mapping.items()
            if v in standard_keys
        }

        print(f"  LLM successfully mapped {len(valid_mapping)} labels.")
        return valid_mapping

    except json.JSONDecodeError:
        print("[WARNING] Could not parse LLM response as JSON. Mapping will be empty.")
        return {}


# ---------------------------------------------------------------------------
# Step D: Main function — get or create mapping
# ---------------------------------------------------------------------------

def get_or_create_mapping(company_name: str, pdf_path: str,
                          target_pages: list) -> dict:
    """
    The main function called by pipeline.py.

    - If configs/metric_mappings/{company}.json already exists:
        Load it and return the mappings dict.

    - If the file does NOT exist:
        1. Extract raw labels from the PDF
        2. Ask the LLM to map them
        3. Save the result as {company}.json for future runs
        4. Return the mappings dict

    This means: for any new company, the first run creates the config
    automatically. Every run after that reuses the saved file instantly.
    """
    config_path = CONFIGS_DIR / f"{company_name.lower()}.json"

    # --- Config already exists: reuse it ---
    if config_path.exists():
        print(f"  Existing mapping config found: {config_path.name}")
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("mappings", {})

    # --- No config: auto-generate ---
    print(f"  No config found for '{company_name}'. Auto-generating with LLM...")

    raw_labels = extract_raw_labels(pdf_path, target_pages)
    print(f"  Found {len(raw_labels)} unique labels in the PDF.")

    mapping = auto_generate_mapping(company_name, raw_labels)

    # Save for future runs
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_data = {
        "company": company_name.lower(),
        "_comment": "Auto-generated by auto_mapper.py using Mistral LLM.",
        "_auto_generated": True,
        "mappings": mapping,
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=4)

    print(f"  Config saved to: {config_path}")
    return mapping
