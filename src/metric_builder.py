"""
metric_builder.py
-----------------
Normalization layer: maps company-specific raw labels to standard keys.

WHY THIS MODULE EXISTS
----------------------
After you extract raw rows from a PDF, each row has a "label" string
taken directly from the document. These labels vary by company:

    Apple:     "total net sales"
    Microsoft: "revenue"
    NVIDIA:    "total revenue"

This module translates all of them to the same standard key: "total_revenue".

HOW IT WORKS — TWO-STAGE LOOKUP
---------------------------------
Stage 1 — Exact match:
    Look up raw_label directly in the company's JSON mapping config.
    This is fast and unambiguous.

Stage 2 — Fuzzy match fallback:
    If exact match fails, use Python's difflib to find the closest
    known label (within a similarity threshold of 0.80).
    This handles minor variations like:
      "Cash And Cash Equivalents" vs "cash and cash equivalents"

FUTURE UPGRADE PATH (vector-based matching)
-------------------------------------------
The fuzzy match stage can be replaced with vector/embedding-based
similarity search later — e.g., using a SentenceTransformer to embed
both the raw label and all known mapping keys, then finding the
nearest neighbor. The interface (normalize_metrics) stays the same.

Usage
-----
    from src.metric_builder import build_normalized_metrics

    # raw_rows: list of dicts from extractor, each with 'label' and 'values'
    metrics = build_normalized_metrics(raw_rows, company_name="apple")
"""

import json
import difflib
from pathlib import Path

from src.schemas.financial_schema import validate_metrics


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

# Path to the configs directory.
# Path(__file__) = .../GraphRAG/src/metric_builder.py
# .parent       = .../GraphRAG/src/
# .parent.parent = .../GraphRAG/
CONFIGS_DIR = Path(__file__).parent.parent / "configs" / "metric_mappings"


def load_mapping_config(company: str) -> dict:
    """
    Load the JSON mapping config for a company and return it as a dict.

    The config maps raw label strings -> standard canonical keys.
    Keys are lowercased here so matching is always case-insensitive.

    Parameters
    ----------
    company : str
        Company name (lowercase), e.g. "apple", "microsoft".

    Returns
    -------
    dict
        {lowercased_raw_label: standard_key, ...}

    Raises
    ------
    FileNotFoundError
        If no config file exists for the company.
    """
    config_path = CONFIGS_DIR / f"{company.lower()}.json"

    if not config_path.exists():
        raise FileNotFoundError(
            f"No mapping config found for company '{company}'.\n"
            f"Expected file: {config_path}\n"
            f"Create it by adding a JSON file with a 'mappings' dict."
        )

    with open(config_path, "r") as f:
        config = json.load(f)

    # Lowercase all mapping keys so matching is case-insensitive.
    # The values (standard keys) remain unchanged.
    return {raw.lower(): standard for raw, standard in config["mappings"].items()}


# ---------------------------------------------------------------------------
# Fuzzy match
# ---------------------------------------------------------------------------

def _fuzzy_match(raw_label: str, mapping: dict, threshold: float = 0.80):
    """
    Find the closest known mapping key using string similarity.

    This is Stage 2 of the lookup, used when exact match fails.
    It uses Python's built-in difflib.SequenceMatcher algorithm
    (similar to edit distance, but optimized for common subsequences).

    The threshold of 0.80 means the raw_label must be at least 80%
    similar to a known key to be accepted. This avoids wrong matches.

    WHY 0.80?
        - 0.90+ is too strict: misses "selling, general & admin" vs
          "selling, general and administrative"
        - 0.70 is too loose: can match unrelated short strings
        - 0.80 is a safe default for financial label variations

    Parameters
    ----------
    raw_label : str
        The label extracted from the PDF (already lowercased).
    mapping : dict
        The company's {raw_label: standard_key} mapping dict.
    threshold : float
        Minimum similarity ratio (0.0–1.0) to accept a match.

    Returns
    -------
    str or None
        The matched standard key if found, else None.
    """
    candidates = list(mapping.keys())

    # get_close_matches returns a list of the best matches.
    # n=1 means we only want the single best match.
    matches = difflib.get_close_matches(raw_label, candidates, n=1, cutoff=threshold)

    if matches:
        matched_label = matches[0]
        similarity = difflib.SequenceMatcher(None, raw_label, matched_label).ratio()
        print(
            f"  [fuzzy]  '{raw_label}'\n"
            f"           -> matched '{matched_label}' (similarity: {similarity:.0%})\n"
            f"           -> standard key: '{mapping[matched_label]}'"
        )
        return mapping[matched_label]

    return None


# ---------------------------------------------------------------------------
# Main normalization function
# ---------------------------------------------------------------------------

def build_normalized_metrics(raw_rows: list, company: str) -> dict:
    """
    Normalize a list of raw extracted rows into a standard-key metrics dict.

    This is the primary function you call after extraction. It:
      1. Loads the company's JSON mapping config.
      2. For each raw row, tries exact match, then fuzzy match.
      3. Builds a metrics dict using standard canonical keys.
      4. Logs any labels it could not map (so you know what to add).
      5. Validates the result against the schema.

    Input Format (raw_rows)
    -----------------------
    Each element in raw_rows should be a dict with:
        - "label"   : str   — raw label text from the PDF
        - "values"  : dict  — {year_str: float}, e.g. {"2023": 383285.0}
        - "source_page" : int   — page number in the PDF (optional)
        - "source_type" : str   — e.g. "pymupdf_financial_line" (optional)

    Output Format
    -------------
    A dict using standard canonical keys:
    {
        "total_revenue": {
            "label": "total net sales",       ← original label preserved
            "values": {"2023": 383285.0, ...},
            "source_page": 51,
            "match_type": "exact"             ← or "fuzzy"
        },
        ...
    }

    Parameters
    ----------
    raw_rows : list[dict]
        Extracted rows from the PDF (output of extractor.assign_years).
    company : str
        Company name — must match a config in configs/metric_mappings/.

    Returns
    -------
    dict
        Standard-key metrics dict ready to save as JSON or pass to engines.
    """
    mapping = load_mapping_config(company)
    normalized = {}
    unmapped = []

    print(f"\nNormalizing {len(raw_rows)} rows for '{company}'...")

    for row in raw_rows:
        raw_label = row["label"].strip().lower()

        # --- Stage 1: Exact match ---
        if raw_label in mapping:
            standard_key = mapping[raw_label]

            # Exact match wins: only store if we don't already have this key.
            # This prevents a later duplicate from overwriting an earlier match.
            if standard_key not in normalized:
                normalized[standard_key] = {
                    "label": row["label"],
                    "values": row["values"],
                    "source_page": row.get("source_page"),
                    "source_type": row.get("source_type", "extracted"),
                    "match_type": "exact",
                }
                print(f"  [exact]  '{raw_label}' -> '{standard_key}'")

        # --- Stage 2: Fuzzy match fallback ---
        else:
            standard_key = _fuzzy_match(raw_label, mapping)

            if standard_key:
                # Fuzzy match only fills a key if it hasn't been filled by
                # an exact match already (exact always takes priority).
                if standard_key not in normalized:
                    normalized[standard_key] = {
                        "label": row["label"],
                        "values": row["values"],
                        "source_page": row.get("source_page"),
                        "source_type": row.get("source_type", "extracted"),
                        "match_type": "fuzzy",
                    }
            else:
                unmapped.append(raw_label)

    # --- Report unmapped labels ---
    if unmapped:
        print(f"\n[WARNING] Could not map {len(unmapped)} label(s) for '{company}':")
        for label in unmapped:
            print(f"  X '{label}'")
        print(
            f"\n  -> To fix: add these to:\n"
            f"    configs/metric_mappings/{company.lower()}.json\n"
        )

    # --- Validate against standard schema ---
    validate_metrics(normalized, company)

    return normalized
