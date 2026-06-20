"""
answer_engine.py
----------------
Functions that detect calculation intent from a natural-language question,
compute a deterministic answer from the metrics JSON, and optionally route
through an LLM (Ollama/Mistral) for a richer final response.

Usage
-----
    from src.answer_engine import answer_financial_question

    answer = answer_financial_question(
        "What was Apple's net profit margin in 2023?",
        metrics=metrics,
        collection=chroma_collection,
        embedding_model=embedding_model,
    )
    print(answer)
"""

import json

# pyrefly: ignore [missing-import]
import ollama

from src.utils import margin, percentage_change, format_money, format_percent
from src.calculation_engine import get_value


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------

def detect_calculation_intent(question):
    """
    Map a natural-language *question* to a calculation intent string.

    Returns
    -------
    str
        One of: ``net_profit_margin``, ``gross_margin_percent``,
        ``operating_margin``, ``rd_as_percent_of_sales``,
        ``research_and_development``, ``revenue_growth``,
        ``net_sales_comparison``, ``liabilities_to_assets``,
        ``cash_to_assets``, or ``rag_only`` (no deterministic calculation).
    """
    q = question.lower()

    if "net profit margin" in q or "net margin" in q:
        return "net_profit_margin"

    if "total revenue" in q or "total sales" in q:
        return "total_revenue"

    if "gross margin" in q:
        return "gross_margin_percent"

    if "operating margin" in q:
        return "operating_margin"

    if "r&d" in q or "research and development" in q:
        if "%" in q or "percentage" in q:
            return "rd_as_percent_of_sales"
        return "research_and_development"

    if "revenue growth" in q or "sales growth" in q:
        return "revenue_growth"

    if "compare" in q and "net sales" in q:
        return "net_sales_comparison"

    if "liabilities to assets" in q:
        return "liabilities_to_assets"

    if "cash to assets" in q:
        return "cash_to_assets"

    # Catch any "profit" question that wasn't matched above.
    # This handles: "what is the profit?", "profit in 2022",
    # "profit in percentages and amount", "how much profit?", etc.
    # Returns BOTH the dollar amount (net income) and the % margin together.
    if "profit" in q or "net income" in q or "earnings" in q:
        return "profit_summary"

    return "rag_only"


# ---------------------------------------------------------------------------
# Deterministic calculator
# ---------------------------------------------------------------------------

def calculate_answer(question, metrics, year=2023):
    """
    Attempt to answer *question* deterministically using *metrics*.

    Parameters
    ----------
    question : str
        The user's natural-language question.
    metrics : dict
        Pre-loaded metrics dictionary.
    year : int, optional
        Primary fiscal year for single-year queries (default: 2023).

    Returns
    -------
    dict or None
        A dict with keys ``intent``, ``answer``, ``calculation``,
        ``values_used``, or ``None`` when intent is ``rag_only``.
    """
    intent = detect_calculation_intent(question)

    def _get(key, yr=year):
        return get_value(key, yr, metrics=metrics)

    if intent == "profit_summary":
        # Returns BOTH net income (dollar amount) AND net profit margin (%).
        # This is what users mean when they ask "what is the profit in amount and %".
        revenue   = _get("total_revenue")
        net_income = _get("net_income")
        pct = margin(net_income, revenue)

        return {
            "intent": intent,
            "answer": (
                f"In {year}, net income (profit) was {format_money(net_income)} million.\n"
                f"Net profit margin was {format_percent(pct)} "
                f"({format_money(net_income)} / {format_money(revenue)} × 100)."
            ),
            "calculation": (
                f"Net income = {format_money(net_income)}M  |  "
                f"Net profit margin = {format_money(net_income)} / {format_money(revenue)} × 100 "
                f"= {format_percent(pct)}"
            ),
            "values_used": {
                f"net_income_{year}": net_income,
                f"total_revenue_{year}": revenue,
            },
        }

    if intent == "net_profit_margin":
        revenue = _get("total_revenue")
        net_income = _get("net_income")
        result = margin(net_income, revenue)

        return {
            "intent": intent,
            "answer": f"Net profit margin in {year} was {format_percent(result)}.",
            "calculation": (
                f"Net profit margin = Net income / Total net sales × 100 "
                f"= {format_money(net_income)} / {format_money(revenue)} × 100 "
                f"= {format_percent(result)}"
            ),
            "values_used": {
                f"net_income_{year}": net_income,
                f"total_net_sales_{year}": revenue,
            },
        }

    if intent == "gross_margin_percent":
        revenue = _get("total_revenue")
        gross_margin = _get("gross_profit")
        result = margin(gross_margin, revenue)

        return {
            "intent": intent,
            "answer": f"Gross margin percentage in {year} was {format_percent(result)}.",
            "calculation": (
                f"Gross margin % = Gross margin / Total net sales × 100 "
                f"= {format_money(gross_margin)} / {format_money(revenue)} × 100 "
                f"= {format_percent(result)}"
            ),
            "values_used": {
                f"gross_margin_{year}": gross_margin,
                f"total_net_sales_{year}": revenue,
            },
        }

    if intent == "operating_margin":
        revenue = _get("total_revenue")
        operating_income = _get("operating_income")
        result = margin(operating_income, revenue)

        return {
            "intent": intent,
            "answer": f"Operating margin in {year} was {format_percent(result)}.",
            "calculation": (
                f"Operating margin = Operating income / Total net sales × 100 "
                f"= {format_money(operating_income)} / {format_money(revenue)} × 100 "
                f"= {format_percent(result)}"
            ),
            "values_used": {
                f"operating_income_{year}": operating_income,
                f"total_net_sales_{year}": revenue,
            },
        }

    if intent == "rd_as_percent_of_sales":
        revenue = _get("total_revenue")
        rd = _get("research_and_development")
        result = margin(rd, revenue)

        return {
            "intent": intent,
            "answer": f"R&D expense as a percentage of sales in {year} was {format_percent(result)}.",
            "calculation": (
                f"R&D as % of sales = Research and development / Total net sales × 100 "
                f"= {format_money(rd)} / {format_money(revenue)} × 100 "
                f"= {format_percent(result)}"
            ),
            "values_used": {
                f"research_and_development_{year}": rd,
                f"total_net_sales_{year}": revenue,
            },
        }

    if intent == "research_and_development":
        rd = _get("research_and_development")
        return {
            "intent": intent,
            "answer": f"Research and development expense in {year} was {format_money(rd)}.",
            "values_used": {f"research_and_development_{year}": rd},
        }

    if intent == "total_revenue":
        revenue = _get("total_revenue")
        return {
            "intent": intent,
            "answer": f"Total revenue in {year} was {format_money(revenue)}.",
            "values_used": {f"total_revenue_{year}": revenue},
        }

    if intent == "revenue_growth":
        revenue_current = _get("total_revenue", year)
        revenue_prev = _get("total_revenue", year - 1)
        change = revenue_current - revenue_prev
        pct_change = percentage_change(revenue_current, revenue_prev)

        return {
            "intent": intent,
            "answer": (
                f"Total net sales changed by {format_percent(pct_change)} "
                f"in {year} compared with {year - 1}."
            ),
            "calculation": (
                f"Revenue growth = ({year} net sales - {year-1} net sales) "
                f"/ {year-1} net sales × 100 "
                f"= ({format_money(revenue_current)} - {format_money(revenue_prev)}) "
                f"/ {format_money(revenue_prev)} × 100 = {format_percent(pct_change)}"
            ),
            "values_used": {
                f"total_net_sales_{year}": revenue_current,
                f"total_net_sales_{year - 1}": revenue_prev,
                "change": change,
            },
        }

    if intent == "net_sales_comparison":
        revenue_current = _get("total_revenue", year)
        revenue_prev = _get("total_revenue", year - 1)
        change = revenue_current - revenue_prev
        pct_change = percentage_change(revenue_current, revenue_prev)

        return {
            "intent": intent,
            "answer": (
                f"Total net sales changed from {format_money(revenue_prev)} "
                f"in {year - 1} to {format_money(revenue_current)} in {year}."
            ),
            "calculation": (
                f"Difference = {format_money(revenue_current)} - {format_money(revenue_prev)} "
                f"= {format_money(change)}. "
                f"Percentage change = {format_percent(pct_change)}."
            ),
            "values_used": {
                f"total_net_sales_{year}": revenue_current,
                f"total_net_sales_{year - 1}": revenue_prev,
                "change": change,
            },
        }

    if intent == "liabilities_to_assets":
        liabilities = _get("total_liabilities")
        assets = _get("total_assets")
        result = margin(liabilities, assets)

        return {
            "intent": intent,
            "answer": f"Liabilities-to-assets ratio in {year} was {format_percent(result)}.",
            "calculation": (
                f"Liabilities to assets = Total liabilities / Total assets × 100 "
                f"= {format_money(liabilities)} / {format_money(assets)} × 100 "
                f"= {format_percent(result)}"
            ),
            "values_used": {
                f"total_liabilities_{year}": liabilities,
                f"total_assets_{year}": assets,
            },
        }

    if intent == "cash_to_assets":
        cash = _get("cash_and_equivalents")
        assets = _get("total_assets")
        result = margin(cash, assets)

        return {
            "intent": intent,
            "answer": f"Cash-to-assets ratio in {year} was {format_percent(result)}.",
            "calculation": (
                f"Cash to assets = Cash and cash equivalents / Total assets × 100 "
                f"= {format_money(cash)} / {format_money(assets)} × 100 "
                f"= {format_percent(result)}"
            ),
            "values_used": {
                f"cash_and_cash_equivalents_{year}": cash,
                f"total_assets_{year}": assets,
            },
        }

    # intent == "rag_only"
    return None


# ---------------------------------------------------------------------------
# LLM interpretation
# ---------------------------------------------------------------------------

def generate_llm_financial_interpretation(summary, model="mistral", temperature=0.2):
    """
    Ask the LLM to interpret a financial summary produced by
    :func:`~src.calculation_engine.build_financial_summary`.

    Parameters
    ----------
    summary : str
        Human-readable financial summary text.
    model : str, optional
        Ollama model name (default: ``"mistral"``).
    temperature : float, optional
        Sampling temperature (default: 0.2).

    Returns
    -------
    str
        LLM interpretation text.
    """
    prompt = f"""
You are a senior equity research analyst.

Interpret the following financial analysis summary.

Rules:
1. Do not make claims not directly supported by the metrics.
2. Do not compare with industry averages unless benchmark data is provided.
3. Do not say liabilities exceed assets unless ratio > 100%.
4. Use cautious analyst-style language.
5. Separate observations from conclusions.

Focus on:
- profitability
- growth
- efficiency
- financial health

Keep the answer concise but insightful.

Financial summary:
{summary}
"""

    response = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": temperature},
    )

    return response["message"]["content"]


# ---------------------------------------------------------------------------
# Full hybrid answer (calculation + RAG + LLM)
# ---------------------------------------------------------------------------

def answer_financial_question(
    question,
    metrics,
    collection,
    embedding_model,
    year=2023,
    llm_model="mistral",
    n_text=5,
    n_tables=5,
):
    """
    Answer *question* by combining a deterministic calculation (when possible)
    with vector-store retrieval and an LLM.

    Parameters
    ----------
    question : str
        The user's natural-language question.
    metrics : dict
        Pre-loaded metrics dictionary.
    collection : chromadb.Collection
        ChromaDB collection to query for retrieved context.
    embedding_model : SentenceTransformer
        Model used to embed the query.
    year : int, optional
        Primary fiscal year for single-year queries (default: 2023).
    llm_model : str, optional
        Ollama model name (default: ``"mistral"``).
    n_text : int, optional
        Number of text-chunk results to retrieve (default: 5).
    n_tables : int, optional
        Number of table-row results to retrieve (default: 5).

    Returns
    -------
    str
        Final answer text from the LLM.
    """
    # --- deterministic calculation ---
    calculation_result = calculate_answer(question, metrics=metrics, year=year)

    # --- vector retrieval ---
    query_embedding = embedding_model.encode(question).tolist()

    text_results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_text,
        where={"type": "text_chunk"},
    )

    table_results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_tables,
        where={"type": "table_row"},
    )

    retrieved = []
    for i in range(len(table_results["documents"][0])):
        retrieved.append({
            "source_type": "table_row",
            "text": table_results["documents"][0][i],
            "page": table_results["metadatas"][0][i]["page"],
            "distance": table_results["distances"][0][i],
        })
    for i in range(len(text_results["documents"][0])):
        retrieved.append({
            "source_type": "text_chunk",
            "text": text_results["documents"][0][i],
            "page": text_results["metadatas"][0][i]["page"],
            "distance": text_results["distances"][0][i],
        })

    context = ""
    for idx, chunk in enumerate(retrieved, start=1):
        context += f"\n[Source {idx} | Page {chunk['page']} | Type: {chunk['source_type']}]\n"
        context += chunk["text"]
        context += "\n"

    # --- build prompt ---
    if calculation_result:
        prompt = f"""
You are a financial report assistant.

CRITICAL: The deterministic calculation result below is the ONLY source of truth for all numbers.
Do NOT report any number from the retrieved context. If the context shows a different number, ignore it.
The retrieved context is for source references only.

Question:
{question}

Deterministic calculation result:
{json.dumps(calculation_result, indent=4)}

Retrieved context (for source references only — never use its numbers):
{context}

Write a clean final answer in this format:

### Answer
[Clear direct answer using ONLY the number from the deterministic result above]

### Values Used
[List values from the deterministic result]

### Calculation
[Show formula and calculation]

### Interpretation
[Brief financial interpretation]

### Sources
[Mention source pages/types from context if available]
"""
    else:
        prompt = f"""
You are a financial report assistant.

Answer the user's question using ONLY the retrieved context from the financial report.

Question:
{question}

Retrieved context:
{context}

Rules:
1. Do not invent numbers.
2. If the answer needs calculation but values are unavailable, say context is insufficient.
3. Use table rows for numbers and text chunks for explanation.
4. Include source references.

Answer:
"""

    response = ollama.chat(
        model=llm_model,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0, "top_p": 0.2},
    )

    return response["message"]["content"]
