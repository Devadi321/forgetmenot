# ForgetMeNot 🧠

**A chat agent whose long-term memory lives in FalkorDB as a graph.**

Tell it things about yourself once, and it remembers them across sessions —
because the memories live in a real graph database, not in the chat history.
It recalls them via graph traversal, and it can forget on command.

Built for **Graph Hacks: Context for AI Agents** (WeMakeDevs × FalkorDB),
Track 2 — **Agent Memory and Coordination**.

## How it works

Every chat message runs this loop:

1. **Extract entities** — the LLM pulls people, places, things, and topics
   out of your message.
2. **Recall** — the agent runs a Cypher traversal (up to 2 hops from matched
   entities) against FalkorDB and injects the matching memories into the
   LLM's context. If nothing matches (e.g. "What do I like?"), it falls back
   to all direct memories so it never answers from nothing.
3. **Reply** — the LLM answers using those memories, and notes when a
   memory informed its answer. It is instructed to never invent personal
   facts — if it doesn't remember, it says so.
4. **Remember** — the LLM extracts new facts as subject–predicate–object
   triples and writes them to the graph as nodes + edges.

Memory persists in FalkorDB, so hitting **New session** only clears the chat
pane — the agent still knows everything you told it before.

## Commands (type in chat)

| Command | What it does |
|---|---|
| `/memories` | List everything stored in the graph |
| `/forget <thing>` | Delete matching memory nodes + edges (e.g. `/forget coffee`) |
| `/graph` | Show the memory graph (nodes + edges) |
| `/reset` | Wipe all memories |
| `/help` | List commands |

## Setup

**1. Start FalkorDB** (Redis + the FalkorDB module):

```bash
docker run -d -p 6379:6379 falkordb/falkordb
```

No Docker? Load the module into a local Redis 8+ server instead:

```bash
# download the module (FalkorDB v4.22.1, Linux x86_64)
curl -sL -o falkordb.so https://github.com/FalkorDB/FalkorDB/releases/download/v4.22.1/falkordb-x64.so
chmod +x falkordb.so
redis-server --port 6379 --daemonize yes --save '' --appendonly no --loadmodule ./falkordb.so
```

**2. Install dependencies:**

```bash
pip install -r requirements.txt
```

**3. Run the app:**

```bash
python app.py
```

Open http://localhost:5058 — the chat UI is a single page, no build step.
Chat replies use the free Pollinations API (no key needed). Optional env
vars: `FALKOR_HOST`, `FALKOR_PORT`, `FALKOR_GRAPH`, `PORT`,
`LLM_API_URL` / `LLM_API_KEY` / `LLM_MODEL` (any OpenAI-compatible API).

## Graph data model

```
(:Person {name: 'User'})  ── the anchor node; everything hangs off it

(User)-[:LIKES | :DISLIKES | :PREFERS]─> (:Preference {value})
(User)-[:INTERESTED_IN | :OWNS | :WORKS_AT]─> (:Topic {name})
(User)-[:KNOWS]─> (:Person {name})
(User)-[:REMEMBER]─> (:Fact {text})        ← verbatim one-sentence facts
(User)-[:HAS_EVENT]─> (:Event {name, date})
```

Example after telling the agent "I love coffee, I work at Coupamini":

```
(User:Person) -[:LIKES]-> (coffee:Preference)
(User:Person) -[:WORKS_AT]-> (Coupamini:Topic)
(User:Person) -[:REMEMBER]-> ("The user likes coffee.":Fact)
(User:Person) -[:REMEMBER]-> ("The user works at Coupamini.":Fact)
```

## Real Cypher queries used

These are copied verbatim from `memory.py` — every memory operation in the
app goes through FalkorDB with these queries.

**Recall — 2-hop traversal from matched entities:**

```cypher
MATCH (u:Person {name: 'User'})-[r1]->(n1)
WHERE toLower(coalesce(n1.name, '')) IN $entities
   OR toLower(coalesce(n1.value, '')) IN $entities
   OR any(e IN $entities WHERE toLower(coalesce(n1.text, '')) CONTAINS e)
OPTIONAL MATCH (n1)-[r2]-(n2)
RETURN n1, type(r1) AS rel1, n2, type(r2) AS rel2
```

**Write a verbatim fact node:**

```cypher
MERGE (u:Person {name: 'User'})
MERGE (f:Fact {text: $text})
MERGE (u)-[:REMEMBER]->(f)
RETURN f
```

**Write a structured triple** (e.g. `LIKES` → `(:Preference {value})`,
`KNOWS` → `(:Person {name})`, `WORKS_AT` → `(:Topic {name})`):

```cypher
MERGE (u:Person {name: 'User'})
MERGE (n:__LABEL__ {__PROP__: $object})
MERGE (u)-[r:__REL__]->(n)
RETURN n
```

(`__LABEL__` / `__PROP__` / `__REL__` are replaced in code with the
predicate's node label, property, and relationship type.)

**List all memories:**

```cypher
MATCH (u:Person {name: 'User'})-[r]->(n)
RETURN type(r) AS rel, labels(n) AS labels, n
ORDER BY rel, coalesce(n.text, coalesce(n.name, n.value))
```

**Forget — delete every memory node mentioning a term:**

```cypher
MATCH (u:Person {name: 'User'})-[r]->(n)
WHERE toLower(coalesce(n.name, '')) CONTAINS toLower($term)
   OR toLower(coalesce(n.value, '')) CONTAINS toLower($term)
   OR toLower(coalesce(n.text, '')) CONTAINS toLower($term)
DETACH DELETE n
RETURN count(n) AS deleted
```

**Whole memory graph (for `/graph`):**

```cypher
MATCH (u:Person {name: 'User'})-[r1]->(n1)
OPTIONAL MATCH (n1)-[r2]-(n2)
RETURN u, r1, n1, r2, n2
```

## Demo — try this

1. `Hi, my name is Adithya and I love coffee. I work at Coupamini.`
   → the agent replies using the facts and saves them (watch "Saved:" under
   its reply, and the memory panel on the right).
2. Click **New session** — the chat clears, but memory lives in FalkorDB.
3. `What do I like and where do I work?`
   → it recalls both facts via graph traversal.
4. `/memories` → lists every stored memory. `/graph` → shows nodes + edges.
5. `/forget coffee` → deletes the coffee memories (node + edges).
6. `What do I like?` → "I don't remember…" — it never invents facts.

Full line-by-line walkthrough: see [DEMO_SCRIPT.md](DEMO_SCRIPT.md).

## AI disclosure

Built with Muse, an AI coding assistant. (Required by the Graph Hacks
rules: AI coding assistants are allowed with disclosure.)

## Project structure

```
app.py                  Flask app + chat API + commands
memory.py               FalkorDB layer — all Cypher queries live here
llm.py                  Pollinations client: entity/fact extraction + replies
templates/index.html    single-page chat UI + memory panel
requirements.txt
DEMO_SCRIPT.md          2-minute demo walkthrough for the video
```
