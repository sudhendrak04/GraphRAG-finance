"""
graph_pipeline.py
-----------------
Orchestrates graph extraction for a company.

Reads text chunks from an existing ChromaDB collection,
runs LLM extraction on each, and stores the result in Neo4j.
"""

from src.graph_extractor import extract_graph_elements
from src.graph_store import GraphStore


def _to_str(val) -> str:
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("name", "") or ""
    return ""


def build_company_graph(
    pipeline_result,
    neo4j_uri:  str,
    neo4j_user: str,
    neo4j_pass: str,
) -> dict:

    company  = pipeline_result.company_name
    collection = pipeline_result.collectionW

    all_chunks = collection.get(where={"type": "text_chunk"})
    texts = all_chunks["documents"]

    total    = len(texts)
    stored   = 0
    skipped  = 0

    with GraphStore(neo4j_uri, neo4j_user, neo4j_pass) as gs:
        for i, chunk in enumerate(texts):
            print(f"  [{i+1}/{total}] extracting...", end="\r")

            extracted = extract_graph_elements(chunk)

            if not extracted["entities"] and not extracted["relationships"]:
                skipped += 1
                continue

            for entity in extracted["entities"]:
                name = _to_str(entity.get("name", ""))
                if not name:
                    continue
                gs.add_entity(name, entity.get("type", "Unknown"), company)

            for rel in extracted["relationships"]:
                if not all(k in rel for k in ("source", "type", "target")):
                    continue
                source = _to_str(rel["source"])
                target = _to_str(rel["target"])
                rel_type = rel["type"] if isinstance(rel["type"], str) else ""
                if not source or not target or not rel_type:
                    continue
                gs.add_relationship(source, rel_type, target, company)

            stored += 1

    print(f"\nDone. {stored}/{total} chunks produced graph data. {skipped} skipped.")
    return {"total": total, "stored": stored, "skipped": skipped}
