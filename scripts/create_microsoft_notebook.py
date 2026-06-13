"""
Helper script to generate the Microsoft pipeline notebook.
Run from project root: .venv\Scripts\python scripts\create_microsoft_notebook.py
"""
import json

cells = []

# --- Cell 0: Title ---
cells.append({
    "cell_type": "markdown",
    "metadata": {},
    "source": [
        "# Microsoft 2023 10-K Pipeline\n",
        "\n",
        "This notebook runs the full extraction and analysis pipeline for Microsoft FY2023.\n",
        "\n",
        "**Key difference from Apple notebooks**: Nothing in the engine code changed.\n",
        "The only difference is `company_name='microsoft'`, which loads the Microsoft\n",
        "mapping config and handles all label differences automatically.\n",
    ],
    "id": "md-intro"
})

# --- Cell 1: Imports ---
cells.append({
    "cell_type": "code",
    "execution_count": None,
    "metadata": {},
    "outputs": [],
    "source": [
        "import sys\n",
        "sys.path.insert(0, '..')\n",
        "\n",
        "import json\n",
        "import pandas as pd\n",
        "\n",
        "from src.extractor import process_company, extract_text_by_page\n",
        "from src.calculation_engine import generate_financial_analysis, build_financial_summary\n",
        "\n",
        "print('Imports OK')\n"
    ],
    "id": "code-imports"
})

# --- Cell 2: Config header ---
cells.append({
    "cell_type": "markdown",
    "metadata": {},
    "source": [
        "## Step 1: Configure the Pipeline\n",
        "\n",
        "**Before running**, open the Microsoft PDF and find the page numbers for:\n",
        "- **Consolidated Statements of Income** (income statement)\n",
        "- **Consolidated Balance Sheets**\n",
        "\n",
        "Set those page numbers in `TARGET_PAGES` below.\n",
    ],
    "id": "md-config"
})

# --- Cell 3: Config ---
cells.append({
    "cell_type": "code",
    "execution_count": None,
    "metadata": {},
    "outputs": [],
    "source": [
        "PDF_PATH = \"../data/Microsoft/microsoft_23'-10k.pdf\"\n",
        "COMPANY  = 'microsoft'\n",
        "YEAR     = 2023\n",
        "SAVE_DIR = '../data/Microsoft'\n",
        "\n",
        "# IMPORTANT: Set these to the actual income statement + balance sheet pages\n",
        "# Use Step 2 below to preview pages and find the right ones\n",
        "TARGET_PAGES = None  # e.g. [49, 50, 51, 52, 53]\n",
        "\n",
        "print(f'Pipeline config: {COMPANY} {YEAR}')\n",
        "print(f'Target pages: {TARGET_PAGES}')\n"
    ],
    "id": "code-config"
})

# --- Cell 4: Page preview header ---
cells.append({
    "cell_type": "markdown",
    "metadata": {},
    "source": [
        "## Step 2: Preview Pages to Find Financial Statements\n",
        "\n",
        "Change `PREVIEW_PAGE` and run this cell to see the raw text of any page.\n",
        "Look for pages that start with 'CONSOLIDATED STATEMENTS OF INCOME' etc.\n",
    ],
    "id": "md-preview"
})

# --- Cell 5: Page preview ---
cells.append({
    "cell_type": "code",
    "execution_count": None,
    "metadata": {},
    "outputs": [],
    "source": [
        "PREVIEW_PAGE = 49  # change this number and re-run\n",
        "\n",
        "pages = extract_text_by_page(PDF_PATH)\n",
        "print(f'Total pages in PDF: {len(pages)}')\n",
        "print(f'\\n--- Page {PREVIEW_PAGE} text (first 2000 chars) ---\\n')\n",
        "print(pages[PREVIEW_PAGE - 1]['text'][:2000])\n"
    ],
    "id": "code-preview"
})

# --- Cell 6: Pipeline header ---
cells.append({
    "cell_type": "markdown",
    "metadata": {},
    "source": [
        "## Step 3: Run the Full Pipeline\n",
        "\n",
        "This calls `process_company()` which runs:\n",
        "1. PDF extraction (PyMuPDF)\n",
        "2. Year column assignment\n",
        "3. Label normalization via `configs/metric_mappings/microsoft.json`\n",
        "4. Schema validation\n",
        "5. Saves raw CSV + metrics JSON to `data/Microsoft/`\n",
    ],
    "id": "md-pipeline"
})

# --- Cell 7: Run pipeline ---
cells.append({
    "cell_type": "code",
    "execution_count": None,
    "metadata": {},
    "outputs": [],
    "source": [
        "metrics = process_company(\n",
        "    company_name=COMPANY,\n",
        "    pdf_path=PDF_PATH,\n",
        "    year=YEAR,\n",
        "    target_pages=TARGET_PAGES,\n",
        "    save_dir=SAVE_DIR,\n",
        ")\n",
        "\n",
        "print('\\nExtracted metrics summary:')\n",
        "for key, val in metrics.items():\n",
        "    yr_val = val['values'].get(str(YEAR), 'N/A')\n",
        "    if isinstance(yr_val, float):\n",
        "        print(f'  {key:<35} {yr_val:>12,.0f} M')\n",
        "    else:\n",
        "        print(f'  {key:<35} {yr_val}')\n"
    ],
    "id": "code-pipeline"
})

# --- Cell 8: Inspect CSV header ---
cells.append({
    "cell_type": "markdown",
    "metadata": {},
    "source": [
        "## Step 4: Inspect Raw Extraction CSV\n",
        "\n",
        "The pipeline saved `data/Microsoft/microsoft_2023_raw_extraction.csv`.\n",
        "\n",
        "Look for:\n",
        "- Labels you expected but are missing (add them to `microsoft.json`)\n",
        "- Garbage rows (footnote numbers extracted as data)\n",
        "- Wrong values (column order issue — adjust `years_in_report`)\n",
    ],
    "id": "md-csv"
})

# --- Cell 9: Inspect CSV ---
cells.append({
    "cell_type": "code",
    "execution_count": None,
    "metadata": {},
    "outputs": [],
    "source": [
        "csv_path = f'../data/Microsoft/microsoft_{YEAR}_raw_extraction.csv'\n",
        "df = pd.read_csv(csv_path)\n",
        "print(f'Raw extraction: {len(df)} rows')\n",
        "df\n"
    ],
    "id": "code-csv"
})

# --- Cell 10: Analysis header ---
cells.append({
    "cell_type": "markdown",
    "metadata": {},
    "source": [
        "## Step 5: Financial Analysis\n",
        "\n",
        "Same `generate_financial_analysis()` and `build_financial_summary()` as Apple.\n",
        "No changes needed in the engine code.\n",
    ],
    "id": "md-analysis"
})

# --- Cell 11: Analysis ---
cells.append({
    "cell_type": "code",
    "execution_count": None,
    "metadata": {},
    "outputs": [],
    "source": [
        "analysis = generate_financial_analysis(YEAR, metrics=metrics)\n",
        "summary  = build_financial_summary(analysis, company_name='Microsoft')\n",
        "print(summary)\n"
    ],
    "id": "code-analysis"
})

# --- Cell 12: Troubleshooting ---
cells.append({
    "cell_type": "markdown",
    "metadata": {},
    "source": [
        "## Troubleshooting\n",
        "\n",
        "| Problem | Fix |\n",
        "|---|---|\n",
        "| Missing metrics after pipeline | Check WARNING output. Add raw labels to `configs/metric_mappings/microsoft.json` |\n",
        "| Values look wrong | Check raw CSV. If column order is wrong, pass `years_in_report=[2023, 2022, 2021]` explicitly |\n",
        "| Fuzzy match picked wrong label | Add the exact raw label to the JSON config (exact match always wins) |\n",
        "| `KeyError` in analysis | Metric is missing from `metrics` dict — fix extraction/mapping first |\n",
    ],
    "id": "md-troubleshoot"
})

nb = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3"
        },
        "language_info": {
            "name": "python",
            "version": "3.11.0"
        }
    },
    "cells": cells
}

output_path = "code/microsoft_pipeline.ipynb"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1)

print(f"Notebook written to: {output_path}")
