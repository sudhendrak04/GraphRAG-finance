"""
calculation_engine.py
----------------------
Functions that load financial metrics and perform calculations
(ratios, growth rates, full analysis, summaries).

Usage
-----
    from src.calculation_engine import (
        get_value,
        generate_financial_analysis,
        build_financial_summary,
        interpret_liabilities_ratio,
    )
"""

import json

from src.utils import (
    percentage_change,
    margin,
    safe_round,
    format_money,
    format_percent,
)


# ---------------------------------------------------------------------------
# Low-level metric accessor
# ---------------------------------------------------------------------------

def get_value(metric_key, year, metrics=None, metrics_path=None):
    """
    Return the numeric value for *metric_key* in *year* from *metrics*.

    Parameters
    ----------
    metric_key : str
        Key in the metrics dict, e.g. "total_net_sales".
    year : int
        Fiscal year, e.g. 2023.
    metrics : dict, optional
        Pre-loaded metrics dictionary.  If None, *metrics_path* must be given.
    metrics_path : str or Path, optional
        Path to the JSON metrics file.  Used only when *metrics* is None.

    Returns
    -------
    float
        The raw value stored in the JSON.
    """
    if metrics is None:
        if metrics_path is None:
            raise ValueError("Either 'metrics' or 'metrics_path' must be provided.")
        with open(metrics_path, "r") as f:
            metrics = json.load(f)

    return metrics[metric_key]["values"][str(year)]


# ---------------------------------------------------------------------------
# Ratio interpretation
# ---------------------------------------------------------------------------

def interpret_liabilities_ratio(ratio):
    """
    Return a plain-English interpretation of the liabilities-to-assets ratio.

    Parameters
    ----------
    ratio : float
        Liabilities-to-assets expressed as a percentage (0–100+).

    Returns
    -------
    str
    """
    if ratio < 50:
        return "The company maintains relatively low liabilities compared to assets."
    elif ratio < 90:
        return (
            "The company carries substantial liabilities relative to assets, "
            "but liabilities remain below total assets."
        )
    else:
        return "The company carries very high liabilities relative to assets."


# ---------------------------------------------------------------------------
# Analysis builder
# ---------------------------------------------------------------------------

def generate_financial_analysis(year, metrics=None, metrics_path=None):
    """
    Calculate key financial ratios and growth metrics for *year*.

    Parameters
    ----------
    year : int
        Fiscal year to analyse (e.g. 2023).  The previous year is used for
        YoY growth calculations.
    metrics : dict, optional
        Pre-loaded metrics dictionary.
    metrics_path : str or Path, optional
        Path to the JSON metrics file.  Used only when *metrics* is None.

    Returns
    -------
    dict
        Nested dict with revenue, net_income, profitability, expense_efficiency,
        and balance_sheet sections.
    """
    if metrics is None:
        if metrics_path is None:
            raise ValueError("Either 'metrics' or 'metrics_path' must be provided.")
        with open(metrics_path, "r") as f:
            metrics = json.load(f)

    def _get(key, yr):
        return get_value(key, yr, metrics=metrics)

    previous_year = year - 1

    # Revenue
    revenue = _get("total_revenue", year)
    prev_revenue = _get("total_revenue", previous_year)
    revenue_growth = percentage_change(revenue, prev_revenue)

    # Net income
    net_income = _get("net_income", year)
    prev_net_income = _get("net_income", previous_year)
    net_income_growth = percentage_change(net_income, prev_net_income)

    # Margins
    gross_margin_value = _get("gross_profit", year)
    operating_income = _get("operating_income", year)

    gross_margin_pct = margin(gross_margin_value, revenue)
    operating_margin_pct = margin(operating_income, revenue)
    net_profit_margin_pct = margin(net_income, revenue)

    # Expenses
    rd = _get("research_and_development", year)
    sga = _get("selling_general_administrative", year)

    # total_operating_expenses: some companies (e.g. Apple) report this as a
    # single line; others (e.g. Microsoft) report only individual items.
    # When the key is absent, compute it as R&D + SG&A.
    try:
        total_opex = _get("total_operating_expenses", year)
    except KeyError:
        total_opex = rd + sga

    rd_pct = margin(rd, revenue)
    sga_pct = margin(sga, revenue)
    opex_pct = margin(total_opex, revenue)

    # Balance sheet
    assets = _get("total_assets", year)
    liabilities = _get("total_liabilities", year)
    cash = _get("cash_and_equivalents", year)

    liabilities_to_assets = margin(liabilities, assets)
    cash_to_assets = margin(cash, assets)

    analysis = {
        "year": year,

        "revenue": {
            "value": revenue,
            "growth_percent": safe_round(revenue_growth),
        },

        "net_income": {
            "value": net_income,
            "growth_percent": safe_round(net_income_growth),
        },

        "profitability": {
            "gross_margin_percent": safe_round(gross_margin_pct),
            "operating_margin_percent": safe_round(operating_margin_pct),
            "net_profit_margin_percent": safe_round(net_profit_margin_pct),
        },

        "expense_efficiency": {
            "rd_as_percent_of_sales": safe_round(rd_pct),
            "sga_as_percent_of_sales": safe_round(sga_pct),
            "operating_expenses_as_percent_of_sales": safe_round(opex_pct),
        },

        "balance_sheet": {
            "liabilities_to_assets_percent": safe_round(liabilities_to_assets),
            "cash_to_assets_percent": safe_round(cash_to_assets),
        },
    }

    return analysis


# ---------------------------------------------------------------------------
# Summary builder
# ---------------------------------------------------------------------------

def build_financial_summary(analysis, company_name="Company"):
    """
    Build a human-readable text summary from an *analysis* dict produced by
    :func:`generate_financial_analysis`.

    Parameters
    ----------
    analysis : dict
        Output of :func:`generate_financial_analysis`.
    company_name : str, optional
        Company name to include in the header (default: "Company").

    Returns
    -------
    str
        Multi-line summary string.
    """
    year = analysis["year"]

    revenue = analysis["revenue"]["value"]
    revenue_growth = analysis["revenue"]["growth_percent"]

    net_income = analysis["net_income"]["value"]
    net_income_growth = analysis["net_income"]["growth_percent"]

    gross_margin = analysis["profitability"]["gross_margin_percent"]
    operating_margin = analysis["profitability"]["operating_margin_percent"]
    net_margin = analysis["profitability"]["net_profit_margin_percent"]

    rd_pct = analysis["expense_efficiency"]["rd_as_percent_of_sales"]

    liabilities_ratio = analysis["balance_sheet"]["liabilities_to_assets_percent"]
    cash_ratio = analysis["balance_sheet"]["cash_to_assets_percent"]

    summary = f"""
{company_name.upper()} FINANCIAL ANALYSIS ({year})

Revenue:
- Revenue: {format_money(revenue)}
- Revenue growth: {format_percent(revenue_growth)}

Net Income:
- Net income: {format_money(net_income)}
- Net income growth: {format_percent(net_income_growth)}

Profitability:
- Gross margin: {format_percent(gross_margin)}
- Operating margin: {format_percent(operating_margin)}
- Net profit margin: {format_percent(net_margin)}

Expense Efficiency:
- R&D as % of sales: {format_percent(rd_pct)}

Balance Sheet:
- Liabilities to assets: {format_percent(liabilities_ratio)}
- Cash to assets: {format_percent(cash_ratio)}
"""

    return summary
