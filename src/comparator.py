"""
comparator.py
-------------
Cross-company financial comparison.

Takes metrics dicts (from PipelineResult.metrics) for multiple
companies and produces side-by-side comparisons as DataFrames
and LLM-generated narrative summaries.

Design principle: this module only needs metrics dicts — it has
no dependency on the pipeline, PDF, or vector store.
"""

import pandas as pd
import ollama

from src.calculation_engine import get_value
from src.utils import margin, percentage_change, format_percent, format_money

def get_metric(metrics: dict, metric_key: str, year: int):
    """
    Safely fetch one raw metric value for one company.

    Returns None if the metric or year doesn't exist — not an error.
    This lets comparison tables show NaN for missing data instead
    of crashing when companies have different reporting formats.

    Example:
        get_metric(apple_metrics, "total_revenue", 2023)
        → 394328.0
    """
    try:
        return metrics[metric_key]["values"][str(year)]
    except KeyError:
        return None

def compare_metric(companies: dict, metric_key: str, year: int) -> dict:
    """
    Compare one metric across multiple companies for a given year.

    Args:
        companies:  dict of {company_name: metrics_dict}
        metric_key: standard key e.g. "total_revenue", "gross_profit"
        year:       fiscal year as int e.g. 2023

    Returns:
        dict of {company_name: value_or_None}

    Example:
        compare_metric(all_metrics, "gross_profit", 2023)
        → {"apple": 169148.0, "microsoft": 146052.0, "nvidia": 15356.0}
    """
    return {
        company: get_metric(metrics, metric_key, year)
        for company, metrics in companies.items()
    }

def build_comparison_table(companies: dict, year: int) -> pd.DataFrame:
    """
    Build a full side-by-side comparison DataFrame for all companies.

    Rows are metrics + derived ratios.
    Columns are company names.
    Missing data shows as NaN (not an error).

    Args:
        companies:  dict of {company_name: metrics_dict}
        year:       fiscal year as int e.g. 2023

    Returns:
        pd.DataFrame with metrics as index and company names as columns
    """
    # ── Raw metrics to compare directly ──────────────────────────────
    raw_metrics = [
        "total_revenue",
        "gross_profit",
        "operating_income",
        "net_income",
        "research_and_development",
        "selling_general_administrative",
        "total_assets",
        "total_liabilities",
    ]

    rows = {}

    # Add each raw metric as a row
    for key in raw_metrics:
        rows[key] = compare_metric(companies, key, year)

    # ── Derived ratios (computed from raw values) ─────────────────────
    for company, metrics in companies.items():
        rev  = get_metric(metrics, "total_revenue",    year)
        gp   = get_metric(metrics, "gross_profit",     year)
        op   = get_metric(metrics, "operating_income", year)
        ni   = get_metric(metrics, "net_income",       year)

        rows.setdefault("gross_margin_%",     {})[company] = margin(gp, rev)
        rows.setdefault("operating_margin_%", {})[company] = margin(op, rev)
        rows.setdefault("net_margin_%",       {})[company] = margin(ni, rev)

    # ── Assemble into DataFrame ───────────────────────────────────────
    df = pd.DataFrame(rows).T          # companies as columns, metrics as rows
    df.index.name = "metric"
    return df

def generate_narrative(df: pd.DataFrame, year: int, model: str = "mistral") -> str:
    """
    Send the comparison table to the local LLM and get a plain-English
    analysis of which company performed best and why.

    The LLM does NOT calculate — it only interprets numbers we already
    computed. This prevents hallucinated arithmetic.

    Args:
        df:    DataFrame from build_comparison_table()
        year:  fiscal year (for context in the prompt)
        model: Ollama model name (default: mistral)

    Returns:
        str — plain-English narrative analysis
    """
    table_text = df.to_string()

    prompt = f"""You are a financial analyst. Below is a side-by-side comparison
of financial metrics for multiple companies in fiscal year {year}.
All dollar values are in millions USD. Margins are percentages.

{table_text}

Write a concise analysis (4-6 sentences) covering:
1. Which company had the highest revenue and profit?
2. Which company was most efficient (best margins)?
3. One notable difference or insight across the companies.

Do not recalculate any numbers. Use only the data shown above.
"""

    response = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return response["message"]["content"]

def compare_ask(question: str, companies: dict, year: int) -> str:
    METRIC_KEYWORDS = {
        "gross margin":           "gross_margin_%",
        "operating margin":       "operating_margin_%",
        "net margin":             "net_margin_%",
        "profit margin":          "net_margin_%",
        "revenue":                "total_revenue",
        "net income":             "net_income",
        "profit":                 "net_income",
        "operating income":       "operating_income",
        "gross profit":           "gross_profit",
        "research and development": "research_and_development",
        "r&d":                    "research_and_development",
        "assets":                 "total_assets",
        "liabilities":            "total_liabilities",
    }

    q = question.lower()
    df = build_comparison_table(companies, year)

    matched_key = None
    for keyword, metric_key in METRIC_KEYWORDS.items():
        if keyword in q:
            matched_key = metric_key
            break

    if matched_key and matched_key in df.index:
        row = df.loc[matched_key]
        lines = [
            f"  {company.title()}: {v:.2f}"
            if pd.notna(v) else f"  {company.title()}: N/A"
            for company, v in row.items()
        ]
        return f"{matched_key.replace('_', ' ').title()} ({year}):\n" + "\n".join(lines)

    return generate_narrative(df, year)
