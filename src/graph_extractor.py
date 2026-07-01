"""
graph_extractor.py
------------------
LLM-based entity and relationship extraction from financial text chunks.

For each text chunk, asks Mistral to return a JSON object with:
  entities:      list of {name, type} found in the text
  relationships: list of {source, type, target} found in the text
"""

import json
import ollama


EXTRACTION_PROMPT = """\
You are a financial knowledge graph builder.

Extract all entities and relationships from the financial text below.

Return ONLY a JSON object — no explanation, no markdown, no extra text.

Format:
{{
  "entities": [
    {{"name": "entity name", "type": "Company|Person|Product|Risk|Location|Regulation|Event"}}
  ],
  "relationships": [
    {{"source": "entity name", "type": "RELATIONSHIP_TYPE", "target": "entity name"}}
  ]
}}

Rules:
1. Only extract entities explicitly mentioned in the text.

2. DIRECTION: The source is the entity that performs the action or holds the relationship.
   Correct examples:
     - "Apple relies on TSMC"        → Apple RELIES_ON TSMC         (Apple is source)
     - "Tim Cook is CEO of Apple"    → Tim Cook LEADS Apple         (Tim Cook is source, Tim Cook leads Apple)
     - "Apple competes with Google"  → Apple COMPETES_WITH Google   (Apple is source)
     - "TSMC is located in Taiwan"   → TSMC LOCATED_IN Taiwan       (TSMC is source)

3. RISKS: Extract risk concepts as Risk-type entities even if they are abstract.
   Examples: "Supply Chain Concentration", "Geopolitical Tension", "Currency Risk", "Regulatory Risk".
   Connect them: the company that faces the risk is the source.
     - "Apple faces supply chain risk" → Apple FACES_RISK Supply Chain Concentration

4. LOCATIONS: If a company or supplier is mentioned in the context of a location, create a LOCATED_IN relationship.

5. Relationship types must be UPPERCASE_WITH_UNDERSCORES.

6. Maximum 10 entities and 15 relationships per chunk.

7. If nothing meaningful is found, return {{"entities": [], "relationships": []}}.

Text:
{chunk}
"""

def extract_graph_elements(chunk: str, model: str = "mistral") -> dict:
    prompt = EXTRACTION_PROMPT.format(chunk=chunk)

    response = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0},
    )

    raw = response["message"]["content"].strip()

    try:
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start == -1 or end == 0:
            return {"entities": [], "relationships": []}
        return json.loads(raw[start:end])
    except json.JSONDecodeError:
        return {"entities": [], "relationships": []}

