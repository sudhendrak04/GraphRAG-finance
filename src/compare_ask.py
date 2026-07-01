"""
compare_ask.py
--------------
Side-by-side comparison of two companies using the hybrid RAG system.

Steps:
  1. Run hybrid_ask() for company A  → answer A
  2. Run hybrid_ask() for company B  → answer B
  3. Pass both answers to a final LLM call for structured comparison
"""

import ollama
from src.hybrid_ask import hybrid_ask


def compare_ask(
    question:   str,
    company_a:  str,
    result_a,
    year_a:     int,
    company_b:  str,
    result_b,
    year_b:     int,
    neo4j_uri:  str,
    neo4j_user: str,
    neo4j_pass: str,
    model:      str = "mistral",
) -> str:

    print(f"Analyzing {company_a}...")
    answer_a = hybrid_ask(question, company_a, result_a,
                          neo4j_uri, neo4j_user, neo4j_pass, year_a, model)

    print(f"Analyzing {company_b}...")
    answer_b = hybrid_ask(question, company_b, result_b,
                          neo4j_uri, neo4j_user, neo4j_pass, year_b, model)

    prompt = f"""You are a financial analyst. Compare two companies based on research below.

Question asked: {question}

--- {company_a.upper()} ---
{answer_a}

--- {company_b.upper()} ---
{answer_b}

Write a structured comparison:
1. {company_a.upper()} summary (2-3 sentences)
2. {company_b.upper()} summary (2-3 sentences)
3. Key differences
4. Which company appears stronger on this question and why
"""

    response = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.1},
    )

    return response["message"]["content"]
