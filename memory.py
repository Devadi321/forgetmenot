"""FalkorDB graph memory layer.

All queries below are real Cypher executed against FalkorDB. The README
quotes them verbatim.

Graph model:
    (:Person {name})            - people; (:Person {name: 'User'}) is the anchor
    (:Preference {value})       - things the user likes/dislikes/prefers
    (:Fact {text})              - verbatim one-sentence facts
    (:Topic {name})             - interests, orgs, things the user owns
    (:Event {name, date})       - dated events

    (User)-[:LIKES|DISLIKES|PREFERS]->(:Preference)
    (User)-[:INTERESTED_IN|OWNS|WORKS_AT]->(:Topic)
    (User)-[:KNOWS]->(:Person)
    (User)-[:REMEMBER]->(:Fact)
    (User)-[:HAS_EVENT]->(:Event)
"""
import os

from falkordb import FalkorDB

GRAPH_NAME = os.environ.get("FALKOR_GRAPH", "forgetmenot")
FALKOR_HOST = os.environ.get("FALKOR_HOST", "localhost")
FALKOR_PORT = int(os.environ.get("FALKOR_PORT", "6379"))

# --- Cypher queries (also quoted in README.md) -------------------------------

# Recall: direct memories attached to the User that match any entity,
# plus everything one more hop away (2-hop traversal). Word-level
# matching ($words) catches cases where the question phrases the
# memory differently, e.g. "favourite football team" vs the stored
# fact "User's favourite football team is Kerala Blasters".
RECALL_QUERY = """
MATCH (u:Person {name: 'User'})-[r1]->(n1)
WHERE toLower(coalesce(n1.name, '')) IN $entities
   OR toLower(coalesce(n1.value, '')) IN $entities
   OR any(e IN $entities WHERE toLower(coalesce(n1.text, '')) CONTAINS e)
   OR any(w IN $words WHERE toLower(coalesce(n1.name, '')) CONTAINS w
      OR toLower(coalesce(n1.value, '')) CONTAINS w
      OR toLower(coalesce(n1.text, '')) CONTAINS w)
OPTIONAL MATCH (n1)-[r2]-(n2)
RETURN n1, type(r1) AS rel1, n2, type(r2) AS rel2
"""

# Write a verbatim fact node attached to the User.
WRITE_FACT_QUERY = """
MERGE (u:Person {name: 'User'})
MERGE (f:Fact {text: $text})
MERGE (u)-[:REMEMBER]->(f)
RETURN f
"""

# Write one structured triple: User -[PREDICATE]-> typed node.
# NOTE: __LABEL__/__PROP__/__REL__ are replaced with .replace() — NOT
# .format() — because the Cypher braces would break str.format().
WRITE_TRIPLE_QUERY = """
MERGE (u:Person {name: 'User'})
MERGE (n:__LABEL__ {__PROP__: $object})
MERGE (u)-[r:__REL__]->(n)
RETURN n
"""

# List every memory directly attached to the User.
LIST_MEMORIES_QUERY = """
MATCH (u:Person {name: 'User'})-[r]->(n)
RETURN type(r) AS rel, labels(n) AS labels, n
ORDER BY rel, coalesce(n.text, coalesce(n.name, n.value))
"""

# Forget: delete every memory node (and its edges) mentioning the term.
FORGET_QUERY = """
MATCH (u:Person {name: 'User'})-[r]->(n)
WHERE toLower(coalesce(n.name, '')) CONTAINS toLower($term)
   OR toLower(coalesce(n.value, '')) CONTAINS toLower($term)
   OR toLower(coalesce(n.text, '')) CONTAINS toLower($term)
DETACH DELETE n
RETURN count(n) AS deleted
"""

# Whole memory graph: User -> 1 hop -> 2 hops, for the /graph view.
GRAPH_QUERY = """
MATCH (u:Person {name: 'User'})-[r1]->(n1)
OPTIONAL MATCH (n1)-[r2]-(n2)
RETURN u, r1, n1, r2, n2
"""

# Wipe everything (used by tests / the reset endpoint).
CLEAR_QUERY = """
MATCH (n) DETACH DELETE n
"""

# Predicate -> (node label, property, relationship type)
PREDICATE_MAP = {
    "LIKES": ("Preference", "value", "LIKES"),
    "DISLIKES": ("Preference", "value", "DISLIKES"),
    "PREFERS": ("Preference", "value", "PREFERS"),
    "INTERESTED_IN": ("Topic", "name", "INTERESTED_IN"),
    "OWNS": ("Topic", "name", "OWNS"),
    "WORKS_AT": ("Topic", "name", "WORKS_AT"),
    "KNOWS": ("Person", "name", "KNOWS"),
    "HAS_EVENT": ("Event", "name", "HAS_EVENT"),
}


class Memory:
    def __init__(self):
        self.db = FalkorDB(host=FALKOR_HOST, port=FALKOR_PORT)
        self.graph = self.db.select_graph(GRAPH_NAME)

    # -- helpers -------------------------------------------------------------
    @staticmethod
    def _describe(node):
        """One readable line for a node, e.g. 'Preference: coffee'."""
        props = node.properties or {}
        label = (node.labels or ["Node"])[0]
        for key in ("text", "name", "value"):
            if props.get(key):
                return f"{label}: {props[key]}"
        return f"{label}: {props}"

    @staticmethod
    def _serialize_node(node):
        return {
            "id": node.id,
            "labels": list(node.labels or []),
            "properties": dict(node.properties or {}),
        }

    # -- core operations -----------------------------------------------------
    def ensure_user(self):
        self.graph.query("MERGE (:Person {name: 'User'})")

    def recall(self, entities):
        """Return readable memory lines relevant to the given entities.

        Entity-matched graph traversal first; if nothing matches (e.g. the
        user asked a general question like "What do I like?"), fall back
        to all direct memories so the agent never answers from nothing.
        """
        if entities:
            lowered = [e.lower() for e in entities if e]
            stopwords = {
                "the", "and", "you", "your", "yours", "what", "whats",
                "what's", "who", "whom", "whose", "when", "where", "which",
                "how", "are", "is", "was", "were", "do", "does", "did",
                "tell", "about", "that", "this", "with", "from", "have",
                "has", "had", "can", "could", "would", "should", "there",
                "their", "them", "then", "than", "for", "not", "but",
                "are", "was", "were", "been", "being", "his", "her",
            }
            words = sorted(
                {
                    w.strip(".,!?\"'()[]")
                    for e in lowered
                    for w in e.split()
                    if len(w) >= 3 and w.strip(".,!?\"'()[]") not in stopwords
                }
            )
            result = self.graph.query(
                RECALL_QUERY, {"entities": lowered, "words": words}
            )
            lines = []
            seen = set()
            for row in result.result_set:
                n1, rel1, n2, rel2 = row
                for node in (n1, n2):
                    if node is None:
                        continue
                    line = self._describe(node)
                    if line not in seen and not line.startswith("Person: User"):
                        seen.add(line)
                        lines.append(line)
            if lines:
                return lines
        # Fallback: every memory directly attached to the User.
        return [m["text"] for m in self.list_memories()]

    def write_fact(self, fact):
        """Store one extracted fact: verbatim Fact node + structured edge."""
        text = fact.get("text", "").strip()
        if not text:
            return
        self.graph.query(WRITE_FACT_QUERY, {"text": text})
        predicate = fact.get("predicate", "").upper()
        obj = fact.get("object", "").strip()
        mapping = PREDICATE_MAP.get(predicate)
        if mapping and obj:
            label, prop, rel = mapping
            query = (
                WRITE_TRIPLE_QUERY.replace("__LABEL__", label)
                .replace("__PROP__", prop)
                .replace("__REL__", rel)
            )
            self.graph.query(query, {"object": obj})

    def write_facts(self, facts):
        for fact in facts:
            self.write_fact(fact)

    def list_memories(self):
        result = self.graph.query(LIST_MEMORIES_QUERY)
        memories = []
        for row in result.result_set:
            rel, _labels, node = row
            memories.append({"rel": rel, "text": self._describe(node)})
        return memories

    def forget(self, term):
        """Delete memories mentioning term. Returns number of nodes deleted."""
        result = self.graph.query(FORGET_QUERY, {"term": term})
        try:
            return int(result.result_set[0][0])
        except Exception:
            return 0

    def get_graph(self):
        """Return {nodes: [...], edges: [...]} for the /graph view."""
        result = self.graph.query(GRAPH_QUERY)
        nodes, edges = {}, []
        seen_edges = set()
        for row in result.result_set:
            u, r1, n1, r2, n2 = row
            for node in (u, n1, n2):
                if node is not None and node.id not in nodes:
                    nodes[node.id] = self._serialize_node(node)
            for rel, src, dst in ((r1, u, n1), (r2, n1, n2)):
                if rel is None:
                    continue
                rel_type = getattr(rel, "relation", None) or getattr(rel, "type", "RELATED")
                # Undirected traversal returns each edge from both sides;
                # dedupe ignoring direction so the UI shows it once.
                key = (rel_type, min(src.id, dst.id), max(src.id, dst.id))
                if key not in seen_edges:
                    seen_edges.add(key)
                    edges.append(
                        {"type": rel_type, "from": src.id, "to": dst.id}
                    )
        return {"nodes": list(nodes.values()), "edges": edges}

    def clear(self):
        self.graph.query(CLEAR_QUERY)
