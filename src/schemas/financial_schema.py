"""
financial_schema.py
-------------------
Defines the STANDARD canonical financial keys for this system.

WHY THIS FILE EXISTS
--------------------
Every company uses different label text in their 10-K filings.
  - Apple  -> "total net sales"
  - Microsoft -> "revenue"
  - NVIDIA -> "total revenue"

Instead of writing company-specific code in the engines,
we define ONE standard vocabulary here. The normalization layer
(metric_builder.py) is responsible for mapping any company's
raw labels into these standard keys.

The engines (calculation_engine.py, answer_engine.py) ONLY ever
use these standard keys. They never know or care about raw labels.

ADDING A NEW METRIC
-------------------
1. Add the key here in STANDARD_SCHEMA.
2. Set required=True if all companies must have it.
3. Add it to the company mapping configs (configs/metric_mappings/).
4. Use it in calculation_engine.py.
"""


# ---------------------------------------------------------------------------
# Standard Schema Definition
# ---------------------------------------------------------------------------

# Each entry describes what the metric means and whether it is mandatory.
# This acts as both documentation and a validation contract.
STANDARD_SCHEMA = {
    "total_revenue": {
        "description": "Total revenue / net sales (top line)",
        "unit": "millions_usd",
        "required": True,
    },
    "gross_profit": {
        "description": "Gross profit (revenue minus cost of revenue / COGS)",
        "unit": "millions_usd",
        "required": True,
    },
    "operating_income": {
        "description": "Operating income / operating profit",
        "unit": "millions_usd",
        "required": True,
    },
    "net_income": {
        "description": "Net income / net earnings (bottom line)",
        "unit": "millions_usd",
        "required": True,
    },
    "research_and_development": {
        "description": "R&D expense",
        "unit": "millions_usd",
        "required": True,
    },
    "selling_general_administrative": {
        "description": "Selling, general and administrative expense (SG&A)",
        "unit": "millions_usd",
        "required": True,
    },
    "total_operating_expenses": {
        "description": "Total operating expenses (R&D + SG&A combined)",
        "unit": "millions_usd",
        "required": True,
    },
    "total_assets": {
        "description": "Total assets (balance sheet)",
        "unit": "millions_usd",
        "required": True,
    },
    "total_liabilities": {
        "description": "Total liabilities (balance sheet)",
        "unit": "millions_usd",
        "required": True,
    },
    "cash_and_equivalents": {
        "description": "Cash and cash equivalents (balance sheet)",
        "unit": "millions_usd",
        "required": True,
    },
}


# ---------------------------------------------------------------------------
# Derived sets (computed once at import time for performance)
# ---------------------------------------------------------------------------

# Set of all keys that MUST be present in a normalized metrics dict.
# Used by validate_metrics() below.
REQUIRED_KEYS = frozenset(
    key for key, meta in STANDARD_SCHEMA.items()
    if meta["required"]
)

# Set of ALL defined keys (required or optional).
ALL_KEYS = frozenset(STANDARD_SCHEMA.keys())


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_metrics(metrics: dict, company: str) -> list:
    """
    Check that all required standard keys are present in *metrics*.

    This is called automatically by metric_builder.build_normalized_metrics()
    after normalization. It prints a warning (not an exception) for missing
    keys so the pipeline doesn't crash — you can still use partial data.

    Parameters
    ----------
    metrics : dict
        Normalized metrics dict (must use standard keys as top-level keys).
    company : str
        Company name for readable warning messages.

    Returns
    -------
    list[str]
        List of missing required keys.
        An empty list means validation passed.

    Example
    -------
    >>> validate_metrics({"total_revenue": {...}}, "microsoft")
    ['gross_profit', 'operating_income', ...]   # still missing keys
    """
    missing = [key for key in REQUIRED_KEYS if key not in metrics]

    if missing:
        print(f"\n[SCHEMA VALIDATION] {company.upper()}: {len(missing)} required key(s) missing:")
        for key in sorted(missing):
            print(f"  - {key}  ({STANDARD_SCHEMA[key]['description']})")
        print(
            f"  -> These metrics were not found or not mapped.\n"
            f"    Check configs/metric_mappings/{company.lower()}.json\n"
        )
    else:
        print(f"[SCHEMA VALIDATION] {company.upper()}: All required metrics present OK")

    return missing
