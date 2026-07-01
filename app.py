"""
app.py
------
Flask backend for GraphRAG financial analysis UI.

Loads both company pipelines at startup, then serves
hybrid_ask and compare_ask via HTTP endpoints.
"""

from flask import Flask, request, jsonify, render_template
from pipeline import run_full_pipeline
from src.hybrid_ask  import hybrid_ask
from src.compare_ask import compare_ask

app = Flask(__name__)

NEO4J = {
    "neo4j_uri" : "bolt://127.0.0.1:7687",
    "neo4j_user": "neo4j",
    "neo4j_pass": "sudhendra@123",
}

print("Loading Apple pipeline...")
apple_result = run_full_pipeline("apple", "data/Apple/Apple23 report.pdf",
                                  2023, rebuild_vectors=False)

print("Loading Microsoft pipeline...")
msft_result  = run_full_pipeline("microsoft", "data/Microsoft/microsoft_23'-10k.pdf",
                                  2023, rebuild_vectors=False)

PIPELINES = {
    "apple":     (apple_result, 2023),
    "microsoft": (msft_result,  2023),
}

print("Ready.")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/ask", methods=["POST"])
def ask():
    data     = request.json
    company  = data.get("company", "apple")
    question = data.get("question", "")

    if company not in PIPELINES:
        return jsonify({"error": f"Unknown company: {company}"}), 400

    result, year = PIPELINES[company]
    answer = hybrid_ask(question, company, result, year=year, **NEO4J)
    return jsonify({"answer": answer})


@app.route("/compare", methods=["POST"])
def compare():
    data     = request.json
    question = data.get("question", "")

    result_a, year_a = PIPELINES["apple"]
    result_b, year_b = PIPELINES["microsoft"]

    answer = compare_ask(
        question,
        "apple",     result_a, year_a,
        "microsoft", result_b, year_b,
        **NEO4J,
    )
    return jsonify({"answer": answer})


if __name__ == "__main__":
    app.run(debug=False, port=5000)
