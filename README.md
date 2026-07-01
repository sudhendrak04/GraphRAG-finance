# GraphRAG Finance

A financial analysis system that combines **Knowledge Graphs**, **Vector RAG**, and **Deterministic Calculations** to answer questions about company financial reports.

Built from scratch — no LangChain, no LlamaIndex. Just Python, Neo4j, ChromaDB, and a local LLM (Mistral via Ollama).

---

## What It Does

Upload a financial PDF (10-K annual report) and ask questions like:

- *"What risks does Apple face in China?"*
- *"Who is the CEO?"*
- *"What is the gross margin?"*
- *"Compare Apple and Microsoft's risk profiles."*

Every answer is sourced from three systems working together:

| Source | Used for |
|---|---|
| Knowledge Graph (Neo4j) | Relationships, risks, people, connections |
| Vector RAG (ChromaDB) | Specific facts, quotes, narrative text |
| Deterministic Engine | Exact financial numbers (revenue, margins) |

---

## Architecture

```
PDF
 +-- ChromaDB (vector store)  ---- Vector RAG path
 +-- financial_metrics.json   ---- Deterministic path
 +-- Neo4j (knowledge graph)  ---- Graph RAG path
          ?
    hybrid_ask() — combines all three ? LLM ? answer
```

---

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) with Mistral pulled (`ollama pull mistral`)
- [Neo4j Desktop](https://neo4j.com/download/) with a local database running on `bolt://localhost:7687`

---

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/sudhendrak04/GraphRAG-finance.git
cd GraphRAG-finance

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt
pip install flask neo4j

# 4. Make sure Ollama is running with Mistral
ollama pull mistral
ollama serve
```

---

## Data

Place your company PDFs in the `data/` folder like this:

```
data/
  Apple/
    Apple23 report.pdf
  Microsoft/
    microsoft_23'-10k.pdf
```

---

## Running

### Step 1 — Build the vector store and extract metrics

Open `code/evaluation.ipynb` and run `run_full_pipeline()` for each company.

### Step 2 — Build the knowledge graph

Open `code/build_company_graph.ipynb` and run `build_company_graph()` for each company.  
This sends every text chunk to Mistral and stores extracted entities/relationships in Neo4j.  
**Note:** This takes 15-30 minutes per company depending on PDF size.

### Step 3 — Start the web UI

```bash
python app.py
```

Open `http://127.0.0.1:5000` in your browser.

---

## Project Structure

```
GraphRAG-finance/
+-- app.py                    Flask backend (3 API routes)
+-- pipeline.py               PDF ingestion, ChromaDB, metrics extraction
+-- requirements.txt
+-- src/
¦   +-- answer_engine.py      Deterministic math + Vector RAG
¦   +-- evaluator.py          Accuracy testing
¦   +-- graph_store.py        Neo4j read/write
¦   +-- graph_extractor.py    LLM-based entity/relationship extraction
¦   +-- graph_pipeline.py     Orchestrates graph building from chunks
¦   +-- graph_ask.py          Graph traversal question answering
¦   +-- hybrid_ask.py         Combines all three sources
¦   +-- compare_ask.py        Side-by-side company comparison
+-- templates/
¦   +-- index.html            Web UI
+-- data/                     Place your PDFs here
```

---

## Neo4j Schema

```
Nodes:   (:Entity {name, type, company})
Edges:   (:Entity)-[:RELATES_TO {type, company}]->(:Entity)
```

Entity types: `Company`, `Person`, `Product`, `Risk`, `Location`, `Regulation`, `Event`

---

## Limitations

- Graph extraction quality depends on Mistral (7B). Larger models give better results.
- Hub nodes (the main company node) have 100+ connections — retrieval is capped at 60 paths per query.
- Graph building is slow locally (~3-5 sec per chunk). Using an API-based model (GPT-4o) reduces this to ~30 min total.

---

## Tech Stack

| Component | Tool |
|---|---|
| PDF parsing | PyMuPDF |
| Vector store | ChromaDB |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) |
| Knowledge graph | Neo4j |
| LLM | Mistral 7B via Ollama |
| Web framework | Flask |
