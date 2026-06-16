"""
pipeline.py
-----------
THE MASTER PIPELINE — the only file you need to call from a notebook.

run_full_pipeline() does everything in one call:
  1. Auto-detect income statement + balance sheet pages
  2. Auto-generate (or load) metric mapping JSON via LLM
  3. Extract metrics from PDF
  4. Calculate financial ratios
  5. Set up ChromaDB vector store
  6. Return everything in a PipelineResult object

ask() lets you ask any financial question about the result.

USAGE (from a notebook):
    import sys
    sys.path.insert(0, '..')

    from pipeline import run_full_pipeline, ask

    result = run_full_pipeline(
        company_name = "tesla",
        pdf_path     = "../data/Tesla/tesla_2023_10k.pdf",
        year         = 2023,
    )

    print(result.summary)
    print(ask("What was Tesla's gross margin?", result))
"""

import json
from pathlib import Path
from dataclasses import dataclass

import ollama

from src.auto_mapper import get_target_pages, get_or_create_mapping
from src.extractor import process_company
from src.calculation_engine import generate_financial_analysis, build_financial_summary
from src.vector_pipeline import setup_company_rag, query_collection
from src.answer_engine import calculate_answer


# Absolute path to vector_db/ — anchored to this file's location.
# Path(__file__) = .../GraphRAG/pipeline.py
# .parent        = .../GraphRAG/   (project root)
# This is always correct regardless of which directory the notebook runs from.
VECTOR_DB_DIR = str(Path(__file__).parent / "vector_db")

# ---------------------------------------------------------------------------
# PipelineResult: a container that holds everything the pipeline produces
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    """
    Everything produced by run_full_pipeline() for one company + year.

    Think of this as the "output package" of the pipeline.
    All subsequent steps (Q&A, evaluation, comparison) read from this object.

    Attributes
    ----------
    company_name : str
        Lowercase company identifier. e.g. "nvidia"
    year : int
        Primary fiscal year. e.g. 2023
    metrics : dict
        Normalized metrics dict using standard keys.
        e.g. {"total_revenue": {"values": {"2023": 26974.0}, ...}, ...}
    analysis : dict
        All calculated financial ratios (margins, growth rates, etc.)
    summary : str
        Human-readable financial summary text. Ready to print or pass to LLM.
    collection : object
        ChromaDB collection for this company. Used by ask() for RAG retrieval.
    embedding_model : object
        SentenceTransformer model. Used by ask() to embed questions.
    pdf_path : str
        Path to the source PDF (stored for reference).
    target_pages : list
        Which pages were used for extraction (auto-detected or provided).
    """
    company_name:    str
    year:            int
    metrics:         dict
    analysis:        dict
    summary:         str
    collection:      object
    embedding_model: object
    pdf_path:        str
    target_pages:    list


# ---------------------------------------------------------------------------
# run_full_pipeline: the one function to call for any company
# ---------------------------------------------------------------------------

def run_full_pipeline(
    company_name:     str,
    pdf_path:         str,
    year:             int,
    target_pages:     list = None,
    years_in_report:  list = None,
    save_dir:         str  = None,
    chroma_path:      str  = None,
    rebuild_vectors:  bool = False,
) -> PipelineResult:
    """
    Full pipeline: PDF -> metrics -> ratios -> vector store -> ready for Q&A.

    For any new company, the only required inputs are:
        company_name, pdf_path, year

    Everything else is automatic.

    Parameters
    ----------
    company_name : str
        Identifier for the company. Use lowercase, no spaces.
        e.g. "nvidia", "apple", "tesla", "microsoft"
        This name is used for:
          - Finding/creating configs/metric_mappings/{company}.json
          - Naming the ChromaDB collection ({company}_{year})
          - Naming saved data files in save_dir

    pdf_path : str
        Path to the 10-K PDF file.
        Can be absolute or relative to where you run the notebook.
        e.g. "../data/Tesla/tesla_2023_10k.pdf"

    year : int
        The primary fiscal year of the report.
        e.g. 2023 for a FY2023 10-K.

    target_pages : list[int], optional
        Page numbers of the income statement + balance sheet.
        DEFAULT: None — pages are AUTO-DETECTED from PDF keywords.
        Only set this manually if auto-detection gets the wrong pages.

    years_in_report : list[int], optional
        The 3 fiscal years shown as columns in the report.
        DEFAULT: [year, year-1, year-2]  e.g. [2023, 2022, 2021]
        Override this for companies with non-standard column order.

    save_dir : str, optional
        Folder to save the raw extraction CSV and metrics JSON.
        DEFAULT: "data/{CompanyName}/"  (created automatically)

    chroma_path : str
        Folder where ChromaDB stores its data files.
        DEFAULT: "vector_db"

    rebuild_vectors : bool
        If True, deletes and re-creates the ChromaDB collection.
        DEFAULT: False — reuses existing collection to save time.
        Set to True if you changed the PDF or want a fresh embedding.

    Returns
    -------
    PipelineResult
        Object containing: metrics, analysis, summary, collection,
        embedding_model, and other metadata.
    """

    pdf_path = str(pdf_path)

    print(f"\n{'=' * 62}")
    print(f"  FULL PIPELINE: {company_name.upper()}  |  FY{year}")
    print(f"{'=' * 62}")

    # ----------------------------------------------------------------
    # Step 1: Auto-detect financial statement pages
    # ----------------------------------------------------------------
    print(f"\n[Step 1/5] Detecting financial statement pages...")

    if target_pages is not None:
        # User provided pages manually — respect their choice
        print(f"  Using manually provided pages: {target_pages}")
    else:
        # Auto-detect from PDF keywords
        target_pages = get_target_pages(pdf_path)

        if target_pages is None:
            # Auto-detection failed — will scan all pages (slower but works)
            print("  No pages detected. Will scan all pages.")

    # ----------------------------------------------------------------
    # Step 2: Auto-generate or load metric mapping config
    # ----------------------------------------------------------------
    print(f"\n[Step 2/5] Loading/generating metric mapping config...")
    get_or_create_mapping(company_name, pdf_path, target_pages)
    #
    # Note: get_or_create_mapping() saves the config to disk if it didn't
    # exist. process_company() in Step 3 will then load it via metric_builder.
    # We don't need to pass the mapping manually — the file path is standard.

    # ----------------------------------------------------------------
    # Step 3: Extract metrics from PDF
    # ----------------------------------------------------------------
    print(f"\n[Step 3/5] Extracting metrics from PDF...")

    if years_in_report is None:
        years_in_report = [year, year - 1, year - 2]

    if save_dir is None:
        # Derive save_dir from the PDF's parent folder.
        # This ensures data is saved alongside the PDF regardless of which
        # directory the notebook is running from.
        save_dir = str(Path(pdf_path).parent)
        Path(save_dir).mkdir(parents=True, exist_ok=True)

    metrics = process_company(
        company_name    = company_name,
        pdf_path        = pdf_path,
        year            = year,
        target_pages    = target_pages,
        years_in_report = years_in_report,
        save_dir        = save_dir,
    )

    # ----------------------------------------------------------------
    # Step 4: Calculate all financial ratios
    # ----------------------------------------------------------------
    print(f"\n[Step 4/5] Calculating financial ratios...")

    analysis = generate_financial_analysis(year, metrics=metrics)
    summary  = build_financial_summary(analysis, company_name=company_name.title())

    print(summary)

    # ----------------------------------------------------------------
    # Step 5: Set up ChromaDB vector store
    # ----------------------------------------------------------------
    print(f"\n[Step 5/5] Setting up vector store (ChromaDB)...")

    if chroma_path is None:
        chroma_path = VECTOR_DB_DIR

    collection, embedding_model = setup_company_rag(
        company_name = company_name,
        pdf_path     = pdf_path,
        metrics      = metrics,
        year         = year,
        chroma_path  = chroma_path,
        rebuild      = rebuild_vectors,
    )

    # ----------------------------------------------------------------
    # Done — print a clean summary
    # ----------------------------------------------------------------
    print(f"\n{'=' * 62}")
    print(f"  Pipeline complete: {company_name.upper()} FY{year}")
    print(f"  Metrics ready    : {list(metrics.keys())}")
    print(f"  Vector store     : {collection.count()} documents in ChromaDB")
    print(f"{'=' * 62}\n")

    return PipelineResult(
        company_name    = company_name,
        year            = year,
        metrics         = metrics,
        analysis        = analysis,
        summary         = summary,
        collection      = collection,
        embedding_model = embedding_model,
        pdf_path        = pdf_path,
        target_pages    = target_pages,
    )


# ---------------------------------------------------------------------------
# ask(): the single Q&A function for any company
# ---------------------------------------------------------------------------

def ask(
    question: str,
    result:   PipelineResult,
    use_llm:  bool = True,
) -> str:
    """
    Ask any financial question about a company.

    HOW IT WORKS (two-step decision):

    Step 1 — Try deterministic calculation first
        If the question matches a known pattern (margin, growth, ratio),
        the calculation engine answers it precisely using the metrics dict.
        The answer is a hard number computed from verified data.

    Step 2 — Fall back to RAG + LLM if no deterministic match
        The question is embedded and compared against all PDF chunks
        in the ChromaDB collection. The top 5 most relevant chunks are
        retrieved and sent to the LLM with a strict prompt that says
        "answer ONLY from the context below."

    This two-step approach means:
        - Financial ratio questions → always deterministic (no hallucination)
        - Text questions (strategy, risks, etc.) → RAG retrieval + LLM

    Parameters
    ----------
    question : str
        Natural language question. e.g.:
        "What was NVIDIA's gross margin in 2023?"
        "What are the main risk factors mentioned in the report?"
        "How did revenue change compared to last year?"

    result : PipelineResult
        Output of run_full_pipeline(). Contains metrics, collection, etc.

    use_llm : bool
        If True (default): LLM adds a 1-2 sentence interpretation
        on top of deterministic answers.
        If False: returns only the raw calculated number.

    Returns
    -------
    str
        The answer as a string. Ready to print.
    """

    # --- Step 1: Deterministic calculation (fast, accurate) ---
    calc = calculate_answer(question, metrics=result.metrics, year=result.year)

    if calc:
        answer = calc["answer"]
        detail = calc.get("calculation", "")

        if use_llm:
            # LLM adds context/interpretation, but CANNOT change the number
            prompt = (
                f"Financial question: {question}\n\n"
                f"Verified answer (do NOT change this): {answer}\n"
                f"Calculation detail: {detail}\n\n"
                f"Add a concise 1-2 sentence analyst interpretation. "
                f"Use only the numbers given above. Do not invent any other data."
            )
            response = ollama.chat(
                model="mistral",
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1},
            )
            llm_note = response["message"]["content"].strip()
            return f"{answer}\n\n{llm_note}"

        return answer

    # --- Step 2: RAG retrieval + LLM (for non-calculation questions) ---
    context_chunks = query_collection(
        question,
        result.collection,
        result.embedding_model,
        n_results=5,
    )

    # Build context string from retrieved chunks
    context_parts = []
    for i, (text, meta) in enumerate(context_chunks, 1):
        page = meta.get("page", "?")
        context_parts.append(f"[Source {i} | Page {page}]\n{text}")

    context = "\n\n".join(context_parts)

    prompt = (
        f"You are a financial analyst assistant.\n\n"
        f"Answer the question using ONLY the context below from the "
        f"{result.company_name.title()} FY{result.year} 10-K annual report.\n\n"
        f"If the context does not contain enough information to answer "
        f"the question, say: 'The report does not provide enough information "
        f"to answer this question.'\n\n"
        f"Do not make up numbers or facts not present in the context.\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {question}\n\n"
        f"Answer:"
    )

    response = ollama.chat(
        model="mistral",
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.2},
    )

    return response["message"]["content"].strip()
