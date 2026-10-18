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
 ├── ChromaDB (vector store)  ──── Vector RAG path
 ├── financial_metrics.json   ──── Deterministic path
 └── Neo4j (knowledge graph)  ──── Graph RAG path
          │
    hybrid_ask() ── combines all three ──> LLM ──> Answer
```

---

## Quickstart with Docker (Recommended)

Docker packages the Flask backend and the Neo4j Enterprise database together, ensuring consistent setup across any machine.

### Prerequisites
1. **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** (must be installed and running).
2. **[Ollama](https://ollama.com/)** with Mistral pulled.

---

### Option A: Running on Your Already Configured Machine

If Docker and the database volume are already initialized:

1. **Start Ollama** in any terminal:
   ```bash
   ollama serve
   ```
2. **Start the containers** from the project directory:
   ```bash
   docker-compose up -d
   ```
3. Open **`http://localhost:5000`** in your browser (allow ~30–45s for the models to load).

**To Stop:**
```bash
docker-compose down
```

---

### Option B: Running on a New PC / After Cloning the Repo

Follow these steps when setting up the project on any new computer:

#### 1. Clone the repository
```bash
git clone https://github.com/sudhendrak04/GraphRAG-finance.git
cd GraphRAG-finance
```

#### 2. Start Ollama and pull Mistral
```bash
ollama pull mistral
ollama serve
```

#### 3. Import the Pre-Built Knowledge Graph (~15 seconds)
A pre-extracted knowledge graph is included as `neo4j.dump` so you don't need to spend 40+ minutes running LLM entity extraction:

**On Windows (PowerShell):**
```powershell
# Start Neo4j
docker-compose up -d neo4j

# Wait 10 seconds, then stop it to unlock the database files
docker-compose stop neo4j

# Load the dump into the Docker volume
docker run --rm -e NEO4J_ACCEPT_LICENSE_AGREEMENT=eval -v graphrag_neo4j_data:/data -v "${PWD}:/dump_source" neo4j:enterprise neo4j-admin database load neo4j --from-path=/dump_source/ --overwrite-destination=true
```

**On Linux / macOS:**
```bash
docker-compose up -d neo4j
sleep 10
docker-compose stop neo4j
docker run --rm -e NEO4J_ACCEPT_LICENSE_AGREEMENT=eval -v graphrag_neo4j_data:/data -v "$(pwd):/dump_source" neo4j:enterprise neo4j-admin database load neo4j --from-path=/dump_source/ --overwrite-destination=true
```

#### 4. Build and Start the Application
```bash
docker-compose up --build -d
```
- First run will take 2–3 minutes while Python dependencies build into the image.
- Watch logs with `docker-compose logs -f app` if desired.
- Open **`http://localhost:5000`** in your browser.

---

## Alternative: Local Python Setup (Without Docker)

If you prefer to run directly in a local virtual environment:

### 1. Requirements
- Python 3.10+
- [Ollama](https://ollama.com) with Mistral (`ollama pull mistral` & `ollama serve`)
- [Neo4j Desktop](https://neo4j.com/download/) running on `bolt://localhost:7687` (password: `sudhendra@123`)

### 2. Environment Setup
```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux

pip install -r requirements.txt
```

### 3. Pipeline Ingestion (One-Time)
- **Vector Store & Metrics**: Run `run_full_pipeline()` in `code/evaluation.ipynb` for each company.
- **Knowledge Graph**: Run `build_company_graph()` in `code/build_company_graph.ipynb`. *(Note: takes 15–30 min per company with local Mistral).*

### 4. Run the UI
```bash
python app.py
```
Open `http://localhost:5000` in your browser.

---

## Project Structure

```
GraphRAG-finance/
├── Dockerfile                Container setup for Flask app
├── docker-compose.yml        Multi-container config (App + Neo4j)
├── neo4j.dump                Pre-built knowledge graph dump (Apple + Microsoft)
├── app.py                    Flask backend & API routes
├── pipeline.py               PDF ingestion, ChromaDB, metrics extraction
├── requirements.txt
├── src/
│   ├── answer_engine.py      Deterministic math + Vector RAG
│   ├── evaluator.py          Accuracy testing
│   ├── graph_store.py        Neo4j read/write operations
│   ├── graph_extractor.py    LLM-based entity & relationship extraction
│   ├── graph_pipeline.py     Orchestrates graph construction
│   ├── graph_ask.py          Graph traversal question answering
│   ├── hybrid_ask.py         Combines all three sources
│   └── compare_ask.py        Cross-company comparison logic
├── templates/
│   └── index.html            Web UI
├── data/                     Financial PDFs (Apple, Microsoft)
└── vector_db/                Persistent ChromaDB stores
```

---

## Neo4j Schema

```cypher
Nodes:   (:Entity {name, type, company})
Edges:   (:Entity)-[:RELATES_TO {type, company}]->(:Entity)
```

**Entity types:** `Company`, `Person`, `Product`, `Risk`, `Location`, `Regulation`, `Event`

---

## Tech Stack

| Component | Tool |
|---|---|
| PDF parsing | PyMuPDF |
| Vector store | ChromaDB |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`) |
| Knowledge graph | Neo4j Enterprise (Docker) |
| Local LLM | Mistral 7B via Ollama |
| Backend & UI | Flask |
| Containerization | Docker & Docker Compose |
