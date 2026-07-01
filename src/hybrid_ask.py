"""
hybrid_ask.py
-------------
Combines Graph RAG + Vector RAG + Deterministic calculation
into a single LLM prompt for higher-quality answers.

Sources used per question:
  1. Graph context   - structured relationships from Neo4j
  2. Vector context  - similar text chunks from ChromaDB
  3. Deterministic   - exact numbers from financial metrics (if intent detected)
"""

import json
import ollama
from src.graph_store import GraphStore
from src.graph_ask  import find_entities_in_question, format_graph_context
from src.answer_engine import detect_calculation_intent, calculate_answer


def get_graph_context(question: str, company: str,
                      neo4j_uri: str, neo4j_user: str, neo4j_pass: str) -> str:
    with GraphStore(neo4j_uri, neo4j_user, neo4j_pass) as gs:
        matched = find_entities_in_question(question, company, gs)
        if not matched:
            return ""
        all_paths = []
        for name in matched:
            all_paths.extend(gs.get_entity_context(name, company, hops=2))
    return format_graph_context(all_paths[:60])

def get_vector_context(question: str, pipeline_result, n_results: int = 5) -> str:
    query_embedding = pipeline_result.embedding_model.encode([question])

    results = pipeline_result.collection.query(
        query_embeddings=query_embedding.tolist(),
        n_results=n_results,
        where={"type": "text_chunk"},
    )

    if not results["documents"] or not results["documents"][0]:
        return ""

    return "\n---\n".join(results["documents"][0])


def get_people_context(company: str, neo4j_uri: str, neo4j_user: str, neo4j_pass: str) -> str:
    leadership_types = ["IS_CEO_OF", "IS_CFO_OF", "IS_COO_OF", "IS_CTO_OF",
                        "LEADS", "LED_BY", "CEO_OF", "OVERSEES",
                        "IS_CHAIR_OF", "IS_DIRECTOR_OF", "CERTIFIES"]
    cypher = """
        MATCH (p:Entity {company: $company})-[r:RELATES_TO]-(n:Entity {company: $company})
        WHERE p.type = "Person" AND r.type IN $leadership_types
        RETURN p.name AS person, r.type AS role, n.name AS org
        LIMIT 25
    """
    with GraphStore(neo4j_uri, neo4j_user, neo4j_pass) as gs:
        with gs.driver.session() as session:
            result = session.run(cypher, company=company, leadership_types=leadership_types)
            rows = [dict(r) for r in result]

    if not rows:
        return ""

    lines = [f"  {r['person']} [{r['role']}] {r['org']}" for r in rows]
    return "[LEADERSHIP & PEOPLE]\n" + "\n".join(lines)

def hybrid_ask(
    question:       str,
    company:        str,
    pipeline_result,
    neo4j_uri:      str,
    neo4j_user:     str,
    neo4j_pass:     str,
    year:           int = 2023,
    model:          str = "mistral",
) -> str:

    graph_ctx  = get_graph_context(question, company, neo4j_uri, neo4j_user, neo4j_pass)
    vector_ctx = get_vector_context(question, pipeline_result)

    _PEOPLE_KEYWORDS = {"ceo", "cfo", "officer", "chief", "president", "lead", "leads", "founder", "executive", "director", "who"}
    q_words = set(question.lower().split())
    people_ctx = ""
    if q_words & _PEOPLE_KEYWORDS:
        people_ctx = get_people_context(company, neo4j_uri, neo4j_user, neo4j_pass)

    intent     = detect_calculation_intent(question)
    det_result = None
    if intent != "rag_only":
        det_result = calculate_answer(question, pipeline_result.metrics, year)

    sections = []
    if det_result:
        sections.append(f"[DETERMINISTIC CALCULATION]\n{json.dumps(det_result, indent=2)}")
    if people_ctx:
        sections.append(people_ctx)
    if graph_ctx:
        sections.append(f"[KNOWLEDGE GRAPH — structured relationships]\n{graph_ctx}")
    if vector_ctx:
        sections.append(f"[DOCUMENT TEXT — similar passages]\n{vector_ctx}")
    if not sections:
        return "Insufficient context to answer the question."

    prompt = f"""You are a financial analyst assistant with three information sources.

Question: {question}

{chr(10).join(sections)}

Instructions:
- DETERMINISTIC CALCULATION: use these numbers as the authoritative answer for any numerical fact.
- KNOWLEDGE GRAPH: use this for relationships, risks, people, connections, and structure.
- DOCUMENT TEXT: use this for specific facts not covered by the above.
- If sources conflict, trust: Deterministic > Knowledge Graph > Document Text.
- State clearly which source supports each part of your answer.
"""

    response = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.1},
    )

    return response["message"]["content"]
