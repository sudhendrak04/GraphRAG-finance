"""
vector_pipeline.py
------------------
Handles the vector store (ChromaDB) side of the pipeline.

What this file does:
1. Splits the full PDF into small text chunks (for RAG retrieval)
2. Converts metrics dict into readable sentences (for metric Q&A)
3. Creates one ChromaDB collection per company+year
4. Embeds everything using SentenceTransformer and stores it
5. Provides a query function to retrieve relevant chunks

Why one collection per company?
    Each company's 10-K is separate data. Keeping them separate means
    queries to "Apple 2023" never accidentally pull results from "NVIDIA 2023".
    In the future, you could merge them for cross-company comparison.
"""

import json
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from src.extractor import extract_text_by_page


# ---------------------------------------------------------------------------
# Step 1: Chunk the full PDF text into overlapping pieces
# ---------------------------------------------------------------------------

def chunk_pdf_text(
    pdf_path: str,
    company_name: str,
    year: int,
    chunk_size: int = 500,
    overlap: int = 50,
) -> list:
    """
    Read every page of the PDF and split the text into overlapping chunks.

    WHY OVERLAPPING?
    ----------------
    If an important sentence falls at the boundary between two chunks,
    overlap ensures it appears fully in at least one chunk. Without
    overlap, the boundary sentence gets cut in half and may not be
    retrieved correctly.

    Parameters
    ----------
    pdf_path : str
        Path to the 10-K PDF.
    company_name : str
        Used as metadata (e.g. "nvidia") on each chunk.
    year : int
        Fiscal year, used as metadata.
    chunk_size : int
        Number of characters per chunk. 500 is a good default.
    overlap : int
        How many characters to repeat between adjacent chunks.

    Returns
    -------
    list of dicts:
        [{"text": "...", "metadata": {"company": ..., "page": ..., ...}}, ...]
    """
    pages = extract_text_by_page(pdf_path)
    chunks = []

    for page_data in pages:
        page_num = page_data["page_number"]
        text = page_data["text"].strip()

        # Skip pages with almost no text (blank pages, image-only pages)
        if len(text) < 50:
            continue

        # Slide a window of size chunk_size across the page text
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk_text = text[start:end].strip()

            if len(chunk_text) > 20:   # skip tiny fragments
                chunks.append({
                    "text": chunk_text,
                    "metadata": {
                        "company":  company_name.lower(),
                        "year":     str(year),
                        "page":     str(page_num),
                        "type":     "text_chunk",
                        "source":   Path(pdf_path).name,
                    }
                })

            # Move forward by (chunk_size - overlap) to create the overlap
            start += chunk_size - overlap

    return chunks


# ---------------------------------------------------------------------------
# Step 2: Convert metrics dict into readable text sentences
# ---------------------------------------------------------------------------

def chunk_metrics_as_text(metrics: dict, company_name: str, year: int) -> list:
    """
    Convert the metrics dictionary into human-readable sentences and
    add them to the vector store alongside the PDF text chunks.

    WHY DO THIS?
    ------------
    The PDF text contains many pages of legal language, footnotes, and
    disclosures. A question like "What was NVIDIA's revenue in 2023?"
    is much more likely to match a sentence like:
        "Nvidia total revenue in 2023 was $26,974 million."
    than to match raw PDF text that says "Revenue  26,974  16,675  16,675".

    Adding metric facts as clean sentences dramatically improves retrieval
    accuracy for financial number questions.

    Returns
    -------
    list of dicts (same format as chunk_pdf_text output)
    """
    chunks = []

    for standard_key, metric_data in metrics.items():
        label  = metric_data.get("label", standard_key)
        values = metric_data.get("values", {})

        for yr, val in values.items():
            if isinstance(val, (int, float)):
                # Build a readable sentence for each year/metric combination
                readable_key = standard_key.replace("_", " ")
                text = (
                    f"{company_name.title()} {readable_key} in {yr} "
                    f"was ${val:,.0f} million. "
                    f"(Source label in 10-K: '{label}')"
                )
                chunks.append({
                    "text": text,
                    "metadata": {
                        "company":    company_name.lower(),
                        "year":       yr,
                        "metric_key": standard_key,
                        "type":       "metric_fact",
                        "source":     "metrics_json",
                    }
                })

    return chunks


# ---------------------------------------------------------------------------
# Step 3: Get or create a ChromaDB collection
# ---------------------------------------------------------------------------

def get_or_create_collection(
    company_name: str,
    year: int,
    chroma_path: str = "vector_db",
):
    """
    Connect to ChromaDB and get (or create) a collection for this company+year.

    Collection naming convention: "{company}_{year}"
    Examples: "nvidia_2023", "apple_2023", "tesla_2024"

    This means:
    - First run: creates a new empty collection
    - Every run after: finds the existing collection (skips re-embedding)

    Returns
    -------
    (client, collection, is_new)
        is_new = True if we just created it (need to embed)
        is_new = False if it already existed (can skip embedding)
    """
    client = chromadb.PersistentClient(path=chroma_path)
    collection_name = f"{company_name.lower()}_{year}"

    # Check if collection already exists
    existing_names = [c.name for c in client.list_collections()]

    if collection_name in existing_names:
        collection = client.get_collection(collection_name)
        print(f"  Found existing collection '{collection_name}' "
              f"({collection.count()} documents)")
        return client, collection, False    # False = already exists

    # Create a new collection
    collection = client.create_collection(
        name=collection_name,
        metadata={
            "company": company_name.lower(),
            "year":    str(year),
        },
    )
    print(f"  Created new collection: '{collection_name}'")
    return client, collection, True         # True = just created


# ---------------------------------------------------------------------------
# Step 4: Embed chunks and store them in ChromaDB
# ---------------------------------------------------------------------------

def embed_and_store(
    chunks: list,
    collection,
    embedding_model,
    batch_size: int = 50,
) -> None:
    """
    Embed all chunks using SentenceTransformer and insert into ChromaDB.

    WHY BATCHES?
    ------------
    Embedding all chunks at once could use too much memory for large PDFs
    (100+ pages). Batching keeps memory usage stable regardless of PDF size.

    Parameters
    ----------
    chunks : list
        Output of chunk_pdf_text() + chunk_metrics_as_text().
    collection : chromadb.Collection
        The ChromaDB collection to insert into.
    embedding_model : SentenceTransformer
        The loaded embedding model.
    batch_size : int
        Number of chunks to embed at once. 50 is safe for most machines.
    """
    total = len(chunks)
    texts     = [c["text"]     for c in chunks]
    metadatas = [c["metadata"] for c in chunks]
    ids       = [f"chunk_{i}"  for i in range(total)]

    print(f"  Embedding {total} chunks in batches of {batch_size}...")

    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)

        batch_texts  = texts[start:end]
        batch_metas  = metadatas[start:end]
        batch_ids    = ids[start:end]

        # Encode returns a numpy array; .tolist() converts to plain Python list
        embeddings = embedding_model.encode(batch_texts).tolist()

        collection.add(
            documents=batch_texts,
            embeddings=embeddings,
            metadatas=batch_metas,
            ids=batch_ids,
        )

        print(f"  Stored {end}/{total} chunks...")

    print(f"  Done. Collection now has {collection.count()} documents total.")


# ---------------------------------------------------------------------------
# Step 5: Main setup function
# ---------------------------------------------------------------------------

def setup_company_rag(
    company_name: str,
    pdf_path: str,
    metrics: dict,
    year: int,
    chroma_path: str = "vector_db",
    rebuild: bool = False,
):
    """
    Full RAG setup for one company. Call this after process_company().

    What it does:
    1. Loads the SentenceTransformer embedding model
    2. Gets or creates the ChromaDB collection for this company+year
    3. If the collection is new (or rebuild=True):
       - Chunks the PDF text
       - Converts metrics to text sentences
       - Embeds everything and stores in ChromaDB
    4. Returns (collection, embedding_model) ready for querying

    Parameters
    ----------
    company_name : str
        e.g. "nvidia"
    pdf_path : str
        Path to the 10-K PDF.
    metrics : dict
        Output of process_company() — the normalized metrics dict.
    year : int
        e.g. 2023
    chroma_path : str
        Folder where ChromaDB stores its data. Default: "vector_db"
    rebuild : bool
        If True, delete and re-create the collection even if it exists.
        Use this after changing the PDF or metrics.

    Returns
    -------
    (collection, embedding_model)
    """
    print(f"\n[RAG Setup] {company_name.upper()} {year}")

    # Load embedding model
    print("  Loading embedding model (all-MiniLM-L6-v2)...")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    # Get or create collection
    client, collection, is_new = get_or_create_collection(
        company_name, year, chroma_path
    )

    # Delete and recreate if rebuild requested
    if rebuild and not is_new:
        print("  rebuild=True: deleting existing collection and re-embedding...")
        client.delete_collection(collection.name)
        collection = client.create_collection(
            name=f"{company_name.lower()}_{year}",
            metadata={"company": company_name.lower(), "year": str(year)},
        )
        is_new = True

    # Skip embedding if collection already has data
    if not is_new:
        print("  Collection already populated. Skipping embedding step.")
        print("  (Pass rebuild=True to force re-embedding)")
        return collection, model

    # Build all chunks
    print("  Chunking PDF text...")
    text_chunks   = chunk_pdf_text(pdf_path, company_name, year)
    print(f"  -> {len(text_chunks)} text chunks from PDF")

    print("  Converting metrics to text sentences...")
    metric_chunks = chunk_metrics_as_text(metrics, company_name, year)
    print(f"  -> {len(metric_chunks)} metric fact sentences")

    all_chunks = text_chunks + metric_chunks
    print(f"  -> {len(all_chunks)} total chunks to embed")

    # Embed and store
    embed_and_store(all_chunks, collection, model)

    return collection, model


# ---------------------------------------------------------------------------
# Query helper
# ---------------------------------------------------------------------------

def query_collection(
    question: str,
    collection,
    embedding_model,
    n_results: int = 5,
) -> list:
    """
    Search the ChromaDB collection for chunks relevant to a question.

    Returns a list of (text, metadata) tuples, most relevant first.

    Parameters
    ----------
    question : str
        Natural language question.
    collection : chromadb.Collection
        The company's ChromaDB collection.
    embedding_model : SentenceTransformer
        Same model used during embedding.
    n_results : int
        How many chunks to retrieve. 5 is a good default.

    Returns
    -------
    list of (text_str, metadata_dict) tuples
    """
    # Embed the question using the same model as the stored chunks
    question_embedding = embedding_model.encode([question]).tolist()

    results = collection.query(
        query_embeddings=question_embedding,
        n_results=n_results,
    )

    docs  = results["documents"][0]
    metas = results["metadatas"][0]

    return list(zip(docs, metas))
