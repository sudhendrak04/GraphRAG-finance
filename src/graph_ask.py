"""
graph_ask.py
------------
Graph-powered question answering for GraphRAG.

Given a natural-language question:
  1. Extract entity names mentioned in the question.
  2. Traverse the Neo4j graph from those entities.
  3. Format the traversal as structured context.
  4. Pass context + question to the LLM for a final answer.
"""

import ollama
from src.graph_store import GraphStore

def find_entities_in_question(question: str, company: str, gs: GraphStore) -> list:
    cypher = """
        MATCH (e:Entity {company: $company})
        WHERE e.name IS NOT NULL
        RETURN e.name AS name
    """
    with gs.driver.session() as session:
        result = session.run(cypher, company=company)
        all_names = [record["name"] for record in result]

    _STOPWORDS = {
        "risk", "risks", "company", "notes", "product", "products",
        "service", "services", "financial", "market", "markets",
        "cost", "costs", "value", "values", "number", "numbers",
        "amount", "amounts", "data", "group", "groups", "entity",
    }

    q_lower = question.lower()
    return [
        name for name in all_names
        if isinstance(name, str)
        and len(name) > 3
        and name.lower() not in _STOPWORDS
        and name.lower() in q_lower
    ]

def format_graph_context(paths: list) -> str:
    if not paths:
        return "No graph context found."

    lines = []
    for p in paths:
        path_str = " → ".join(p["path"])
        lines.append(
            f"  {p['source']} --[{path_str}]--> {p['target']}"
        )

    return "\n".join(lines)

def graph_ask(
    question:   str,
    company:    str,
    neo4j_uri:  str,
    neo4j_user: str,
    neo4j_pass: str,
    model:      str = "mistral",
) -> str:

    with GraphStore(neo4j_uri, neo4j_user, neo4j_pass) as gs:

        matched = find_entities_in_question(question, company, gs)
        print(f"Matched entities: {matched}")

        if not matched:
            return "No entities from the knowledge graph matched this question."

        all_paths = []
        for entity_name in matched:
            paths = gs.get_entity_context(entity_name, company, hops=2)
            all_paths.extend(paths)

        graph_context = format_graph_context(all_paths[:80])

    prompt = f"""You are a financial analyst assistant.

Answer the question using ONLY the knowledge graph context below.
Each line shows a relationship path extracted from financial reports.
The format is: Entity --[RELATIONSHIP]--> Connected Entity

Question: {question}

Knowledge graph context:
{graph_context}

Instructions:
- Answer directly based on the relationships shown.
- Group related findings together.
- If the graph context is insufficient, say so.
"""

    response = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.1},
    )

    return response["message"]["content"]
