"""
evaluator.py
------------
Automated evaluation pipeline for the financial Q&A system.

Tests answer_financial_question() against a set of questions
with known expected answers and scores the results.

Two question types:
  deterministic - expected a specific number (within tolerance)
  rag           - expected specific keywords in the response
"""

import re
import json
from pathlib import Path

from src.answer_engine import answer_financial_question

def load_eval_questions(eval_path: str) -> list:
    return json.loads(Path(eval_path).read_text(encoding="utf-8"))

def extract_numbers(response: str) -> list:
    matches = re.findall(r'[\d,]+\.?\d*', response)
    results = []
    for m in matches:
        try:
            results.append(float(m.replace(',', '')))
        except ValueError:
            pass
    return results

def evaluate_one(test_case: dict, pipeline_result) -> dict:
    question = test_case["question"]
    q_type   = test_case["type"]
    year     = test_case.get("year", 2023)
    response = answer_financial_question(
        question,
        pipeline_result.metrics,
        pipeline_result.collection,
        pipeline_result.embedding_model,
        year=year,
    )

    if q_type == "deterministic":
        expected  = test_case["expected_value"]
        tolerance = test_case.get("tolerance", 0.1)
        found     = extract_numbers(response)
        passed    = any(abs(n - expected) <= tolerance for n in found)
        return {
            "question":     question,
            "type":         q_type,
            "response":     response,
            "expected":     expected,
            "found_numbers": found,
            "passed":       passed,
        }

    if q_type == "rag":
        keywords    = test_case["expected_keywords"]
        min_kw      = test_case.get("min_keywords", 1)
        r_lower     = response.lower()
        found_kw    = [kw for kw in keywords if kw.lower() in r_lower]
        passed      = len(found_kw) >= min_kw
        return {
            "question":        question,
            "type":            q_type,
            "response":        response,
            "expected_keywords": keywords,
            "found_keywords":  found_kw,
            "passed":          passed,
        }

    return {"question": question, "type": q_type, "passed": False, "error": "unknown type"}

def run_evaluation(eval_path: str, pipeline_result, company: str = "") -> dict:
    questions = load_eval_questions(eval_path)
    results   = []

    print(f"\n{'='*60}")
    print(f"EVALUATION REPORT  {company.upper()}")
    print(f"{'='*60}\n")

    for test_case in questions:
        result = evaluate_one(test_case, pipeline_result)
        results.append(result)

        status = "PASS" if result["passed"] else "FAIL"
        print(f"[{status}] {result['question']}")

        if result["type"] == "deterministic":
            print(f"       Expected: {result['expected']} | Found in response: {result['found_numbers']}")
        elif result["type"] == "rag":
            total = len(result["expected_keywords"])
            found = len(result["found_keywords"])
            print(f"       Keywords: {found}/{total} found {result['found_keywords']}")

        print()

    passed = sum(1 for r in results if r["passed"])
    total  = len(results)
    pct    = (passed / total * 100) if total > 0 else 0

    print(f"{'='*60}")
    print(f"SCORE: {passed}/{total}  ({pct:.1f}%)")
    print(f"{'='*60}\n")

    return {"passed": passed, "total": total, "accuracy": pct, "results": results}
