"""
extractor.py
------------
Reusable PDF extraction pipeline.

Entry point: process_company(company_name, pdf_path, year)

WHAT THIS MODULE DOES
---------------------
This module handles the HOW of reading a PDF.
It does NOT know or care about what the labels mean.
That is metric_builder.py's job.

The pipeline inside process_company():
  PDF -> raw financial lines -> year-assigned rows -> [metric_builder] -> metrics dict

DESIGN DECISIONS
----------------
1. Always starts from PDF (no CSV required as input).
   Reason: real users have the PDF, not a pre-processed CSV.

2. Saves a debug CSV alongside the metrics JSON.
   Reason: lets you inspect the raw extraction and catch issues
   before normalization. You saw this was valuable during Apple work.

3. target_pages parameter:
   Scanning the entire 100+ page 10-K is slow and produces noise.
   Passing specific page numbers (e.g. income statement pages) gives
   faster, cleaner extraction. You find these by opening the PDF and
   noting which pages contain the financial tables.

4. years_in_report parameter:
   10-K reports show 3 years of data side by side. The order is
   always newest-first: [current_year, current_year-1, current_year-2].
   This maps numeric columns to years correctly.

Usage (from a Jupyter notebook)
---------------------------------
    from src.extractor import process_company

    metrics = process_company(
        company_name="microsoft",
        pdf_path="data/Microsoft/microsoft_23'-10k.pdf",
        year=2023,
        target_pages=[49, 50, 51, 52, 53],   # income stmt + balance sheet pages
        save_dir="data/Microsoft",
    )
"""

import re
import json
import csv
from pathlib import Path

import fitz  # PyMuPDF

from src.utils import clean_number
from src.metric_builder import build_normalized_metrics


# ---------------------------------------------------------------------------
# Step 1: PDF Text Extraction
# ---------------------------------------------------------------------------

def extract_text_by_page(pdf_path: str) -> list:
    """
    Open a PDF and extract all text, page by page.

    This is a low-level function — it just reads the PDF and returns
    raw text. No interpretation happens here.

    Parameters
    ----------
    pdf_path : str
        Absolute or relative path to the PDF file.

    Returns
    -------
    list[dict]
        One dict per page:
        {
            "page_number": int,   ← 1-indexed
            "text": str           ← full text of that page
        }
    """
    doc = fitz.open(pdf_path)
    pages = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        pages.append({
            "page_number": page_idx + 1,     # convert 0-indexed to 1-indexed
            "text": page.get_text(),
        })

    doc.close()
    print(f"  Opened PDF: {Path(pdf_path).name} ({len(pages)} pages total)")
    return pages


# ---------------------------------------------------------------------------
# Step 2: Financial Line Detection
# ---------------------------------------------------------------------------

# A "financial line" must contain at least one number with 3+ digits.
# This pattern matches things like: 383,285 or 114,301 or 29,915
# It would NOT match: "page 2" or "Note 1" (too small).
FINANCIAL_NUMBER_PATTERN = re.compile(r'\d{1,3}(?:,\d{3})+|\d{4,}')


def _extract_numbers_from_line(line: str) -> list:
    """
    Pull all numeric values out of a line in left-to-right order.

    Handles:
    - Commas as thousand separators: "383,285" -> 383285.0
    - Parentheses as negatives: "(11,043)" -> -11043.0
    - Dollar signs (ignored): "$383,285"
    """
    line = line.replace("$", "").replace("%", "")
    numbers = []
    tokens = re.findall(r'\(\s*[\d,]+\s*\)|[\d,]+', line)

    for token in tokens:
        token = token.strip()
        try:
            if token.startswith("(") and token.endswith(")"):
                value = -float(token.strip("()").replace(",", ""))
            else:
                value = float(token.replace(",", ""))
            # Skip page numbers and footnote refs (real financial values >= 100)
            if abs(value) >= 100:
                numbers.append(value)
        except ValueError:
            continue

    return numbers


def _extract_label_from_line(line: str) -> str:
    """
    Extract the text label from the start of a reconstructed row.
    Returns everything before the first digit sequence.
    """
    match = re.match(r'^([A-Za-z][A-Za-z\s,&/\-–()\'.]+)', line)
    if not match:
        return ""
    return match.group(1).strip().rstrip(".,: ")


def extract_financial_lines(pdf_path: str, target_pages: list = None) -> list:
    """
    Scan a PDF and extract rows that look like financial statement entries.

    IMPORTANT LIMITATION
    --------------------
    This heuristic works well for income statement and balance sheet pages
    where each line is "Label   Value1   Value2   Value3".
    It may struggle with complex multi-line table headers or footnotes.
    You will likely need to review the raw output CSV and tweak target_pages.
    This is expected — it's part of the process for each new company.

    Parameters
    ----------
    pdf_path : str
        Path to the 10-K PDF.
    target_pages : list[int], optional
        Page numbers to scan (1-indexed). Strongly recommended to set this
        to just the financial statement pages to reduce noise.
        If None, scans every page (slower, more false positives).

    Returns
    -------
    list[dict]
        Each dict:
        {
            "label": str,
            "raw_numbers": list[float],   ← numbers in column order
            "source_page": int,
            "source_type": "pymupdf_financial_line"
        }
    """
    from collections import defaultdict

    doc = fitz.open(pdf_path)
    raw_rows = []
    skipped = 0

    print(f"  Opened PDF: {Path(pdf_path).name} ({len(doc)} pages total)")

    for page_idx in range(len(doc)):
        page_num = page_idx + 1

        if target_pages and page_num not in target_pages:
            continue

        page = doc[page_idx]

        # get_text("words") returns one tuple per word:
        # (x0, y0, x1, y1, "word_text", block_no, line_no, word_no)
        #
        # WHY NOT get_text()? Because for financial PDFs, the label text
        # ("Total revenue") and the number columns ("211,915", "198,270") are
        # stored as SEPARATE positioned text elements. get_text() outputs them
        # on different \n lines, so label + numbers never appear together.
        # get_text("words") gives us each word's (x, y) position so we can
        # group words that share the same Y coordinate into one row.
        words = page.get_text("words")

        if not words:
            continue

        # Group words by Y position (rounded to 4px buckets to absorb
        # minor vertical misalignment between text in different columns)
        y_buckets = defaultdict(list)
        for word_data in words:
            x0, y0, x1, y1, word_text = word_data[:5]
            y_key = round(y0 / 8) * 8
            y_buckets[y_key].append((x0, word_text))

        # Reconstruct each table row: sort words by X (left -> right), join
        for y_key in sorted(y_buckets.keys()):
            words_in_row = sorted(y_buckets[y_key], key=lambda t: t[0])
            line = " ".join(w for _, w in words_in_row).strip()

            # Must start with a letter (has a label)
            if not line or not line[0].isalpha():
                skipped += 1
                continue

            # Must contain at least one large number
            if not FINANCIAL_NUMBER_PATTERN.search(line):
                skipped += 1
                continue

            label = _extract_label_from_line(line)
            numbers = _extract_numbers_from_line(line)

            if not label or len(label) < 3:
                skipped += 1
                continue

            if len(numbers) == 0 or len(numbers) > 5:
                skipped += 1
                continue

            raw_rows.append({
                "label": label,
                "raw_numbers": numbers,
                "source_page": page_num,
                "source_type": "pymupdf_financial_line",
            })

    doc.close()
    print(f"  Extracted {len(raw_rows)} candidate financial lines ({skipped} rows skipped)")
    return raw_rows



# ---------------------------------------------------------------------------
# Step 3: Map Columns to Fiscal Years
# ---------------------------------------------------------------------------

def assign_years(raw_rows: list, years: list) -> list:
    """
    Map the numeric columns in each row to fiscal years.

    10-K reports present data as columns (newest year first):

        Label          | FY2023  | FY2022  | FY2021
        ───────────────────────────────────────────
        Total revenue  | 383,285 | 394,328 | 365,817

    This function takes the list of raw_numbers [383285, 394328, 365817]
    and maps them to years [2023, 2022, 2021], producing:
        {"2023": 383285.0, "2022": 394328.0, "2021": 365817.0}

    Parameters
    ----------
    raw_rows : list[dict]
        Output of extract_financial_lines(). Each row has "raw_numbers".
    years : list[int]
        Fiscal years in column order (newest first), e.g. [2023, 2022, 2021].

    Returns
    -------
    list[dict]
        Same rows, each now having a "values" dict instead of "raw_numbers".
        Rows with no mappable values are dropped.
    """
    result = []

    for row in raw_rows:
        numbers = row["raw_numbers"]
        values = {}

        # Map index 0 -> years[0], index 1 -> years[1], etc.
        # If a row has fewer columns than years, we just map what we have.
        for i, year in enumerate(years):
            if i < len(numbers):
                values[str(year)] = numbers[i]

        # Only keep rows that got at least one year mapped
        if values:
            result.append({
                "label": row["label"],
                "values": values,
                "source_page": row["source_page"],
                "source_type": row["source_type"],
            })

    print(f"  Year mapping complete: {len(result)} rows with {len(years)}-year values")
    return result


# ---------------------------------------------------------------------------
# Debug helper: Save raw extraction CSV
# ---------------------------------------------------------------------------

def save_raw_csv(raw_rows: list, save_path: str) -> None:
    """
    Save raw extracted rows to a CSV file for inspection.

    WHY WE SAVE A CSV
    -----------------
    Before normalization, you want to see exactly what the extractor found.
    This lets you:
    - Verify that the right labels were picked up
    - Spot garbage rows (headers, footnotes extracted as data)
    - Debug year mapping issues
    - Decide if target_pages needs to be adjusted

    Parameters
    ----------
    raw_rows : list[dict]
        Output of assign_years(). Each row has "label", "values", "source_page".
    save_path : str
        Path to write the CSV file.
    """
    if not raw_rows:
        return

    # Collect all year columns present across all rows
    all_years = sorted(
        {year for row in raw_rows for year in row["values"].keys()},
        reverse=True
    )

    with open(save_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # Header row
        writer.writerow(["label", "source_page"] + all_years)

        # Data rows
        for row in raw_rows:
            year_values = [row["values"].get(year, "") for year in all_years]
            writer.writerow([row["label"], row.get("source_page", "")] + year_values)

    print(f"  [Debug CSV saved] -> {save_path}")


# ---------------------------------------------------------------------------
# Main pipeline entry point
# ---------------------------------------------------------------------------

def process_company(
    company_name: str,
    pdf_path: str,
    year: int,
    target_pages: list = None,
    years_in_report: list = None,
    save_dir: str = None,
) -> dict:
    """
    Full reusable pipeline: PDF -> normalized standard-key metrics dict.

    This is the ONLY function you need to call from your notebooks.
    It orchestrates all steps:
      1. Extract raw financial lines from PDF (PyMuPDF)
      2. Assign fiscal years to numeric columns
      3. Save raw debug CSV (optional, recommended)
      4. Normalize labels -> standard keys (via metric_builder)
      5. Save final metrics JSON (optional)
      6. Return the metrics dict

    Parameters
    ----------
    company_name : str
        Must match a config in configs/metric_mappings/.
        e.g. "apple", "microsoft"  (lowercase)
    pdf_path : str
        Path to the 10-K PDF.
    year : int
        Primary fiscal year of the report (e.g. 2023).
    target_pages : list[int], optional
        Page numbers to scan (1-indexed, based on PDF page numbering).
        Strongly recommended: narrow to financial statement pages.
        Tip: Open the PDF, find the income statement and balance sheet
        sections, note the page numbers.
        Example: [49, 50, 51, 52] for Microsoft FY2023
        If None: scans the entire PDF (slower, more noise).
    years_in_report : list[int], optional
        Fiscal years in column order (newest first).
        Defaults to [year, year-1, year-2] (standard 3-year 10-K comparison).
    save_dir : str, optional
        Directory to save the raw debug CSV and final metrics JSON.
        Recommended: "data/CompanyName/"
        If None: metrics are returned but not saved to disk.

    Returns
    -------
    dict
        Normalized metrics dict using standard keys.
        Ready to pass directly to calculation_engine or answer_engine.

    Example
    -------
        from src.extractor import process_company

        metrics = process_company(
            company_name="microsoft",
            pdf_path="data/Microsoft/microsoft_23'-10k.pdf",
            year=2023,
            target_pages=[49, 50, 51, 52, 53],
            save_dir="data/Microsoft",
        )
    """
    pdf_path = Path(pdf_path)

    # Default: report covers 3 years (standard 10-K format)
    if years_in_report is None:
        years_in_report = [year, year - 1, year - 2]

    print(f"\n{'=' * 60}")
    print(f"  Company : {company_name.upper()}")
    print(f"  PDF     : {pdf_path.name}")
    print(f"  Year    : {year}  |  Columns: {years_in_report}")
    if target_pages:
        print(f"  Pages   : {target_pages}")
    else:
        print(f"  Pages   : ALL (consider narrowing with target_pages)")
    print(f"{'=' * 60}\n")

    # --- Step 1: Extract raw lines from PDF ---
    print("[Step 1/4] Extracting financial lines from PDF...")
    raw_rows = extract_financial_lines(str(pdf_path), target_pages=target_pages)

    # --- Step 2: Assign fiscal years to columns ---
    print(f"\n[Step 2/4] Assigning fiscal years to numeric columns...")
    rows_with_years = assign_years(raw_rows, years_in_report)

    # --- Step 3: Save debug CSV ---
    if save_dir:
        csv_path = Path(save_dir) / f"{company_name.lower()}_{year}_raw_extraction.csv"
        print(f"\n[Step 3/4] Saving raw extraction CSV for inspection...")
        save_raw_csv(rows_with_years, str(csv_path))
    else:
        print(f"\n[Step 3/4] Skipping CSV save (no save_dir provided)")

    # --- Step 4: Normalize labels -> standard keys ---
    print(f"\n[Step 4/4] Normalizing labels using mapping config...")
    metrics = build_normalized_metrics(rows_with_years, company_name)

    # --- Save final metrics JSON ---
    if save_dir:
        json_path = Path(save_dir) / f"{company_name.lower()}_{year}_financial_metrics.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=4)
        print(f"\n[Saved] Metrics JSON -> {json_path}")

    print(f"\n{'=' * 60}")
    print(f"  Pipeline complete: {company_name.upper()} {year}")
    print(f"  Metrics ready: {list(metrics.keys())}")
    print(f"{'=' * 60}\n")

    return metrics
