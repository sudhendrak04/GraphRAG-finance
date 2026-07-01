"""
graph_store.py
--------------
Neo4j connection and graph operations for GraphRAG.

Two responsibilities:
  WRITE: Store extracted entities and relationships.
  READ:  Traverse the graph to get structured context for a question.

Schema:
  Nodes:  (:Entity {name, type, company})
  Edges:  (:Entity)-[:RELATES_TO {type, company}]->(:Entity)
"""

from neo4j import GraphDatabase


class GraphStore:

    def __init__(self, uri: str, username: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(username, password))

    def close(self):
        self.driver.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def add_entity(self, name: str, entity_type: str, company: str) -> None:
        cypher = """
            MERGE (e:Entity {name: $name, company: $company}) 
            SET e.type = $entity_type
        """
        #This is a parameterized query. Never build Cypher with string formatting ("f")
        with self.driver.session() as session:
            session.run(cypher, name=name, entity_type=entity_type, company=company)

    def add_relationship(self, source: str, rel_type: str, target: str, company: str) -> None:
        cypher = """
            MERGE (a:Entity {name: $source, company: $company})
            MERGE (b:Entity {name: $target, company: $company})
            MERGE (a)-[:RELATES_TO {type: $rel_type, company: $company}]->(b)
        """
        with self.driver.session() as session:
            session.run(cypher, source=source, rel_type=rel_type, target=target, company=company)

    def get_entity_context(self, entity_name: str, company: str, hops: int = 2) -> list:
        cypher = """
            MATCH (start:Entity {name: $name, company: $company})
            MATCH (start)-[r:RELATES_TO*1..2]-(connected)
            RETURN start.name AS source,
                   [rel in r | rel.type] AS path,
                   connected.name AS target,
                   connected.type AS target_type
        """
        with self.driver.session() as session:
            result = session.run(cypher, name=entity_name, company=company)
            return [dict(record) for record in result]






            
