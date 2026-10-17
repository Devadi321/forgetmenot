"""ForgetMeNot — a chat agent whose long-term memory lives in FalkorDB as a graph.

Every chat message is run through the loop:
  1. Extract entities from the message (LLM).
  2. Recall relevant memories from FalkorDB via Cypher graph traversal
     (up to 2 hops from matched entities) and inject them into context.
  3. LLM replies using those memories.
  4. LLM extracts new facts as triples and writes them to the graph.
"""
import json
import os

import requests

API_URL = os.environ.get("LLM_API_URL", "https://text.pollinations.ai/openai").rstrip("/")
API_KEY = os.environ.get("LLM_API_KEY", "")
MODEL = os.environ.get("LLM_MODEL", "openai")


def _chat(messages, max_tokens=800, temperature=0.3):
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    r = requests.post(API_URL, json=payload, headers=headers, timeout=90)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def _json_from(text):
    """Pull the first JSON array/object out of an LLM reply."""
    start = min(
        [i for i in (text.find("["), text.find("{")) if i != -1],
        default=-1,
    )
    if start == -1:
        return None
    try:
        return json.loads(text[start:])
    except json.JSONDecodeError:
        return None


def extract_entities(message):
    """Return a list of entity strings (people, places, things, topics)."""
    try:
        out = _chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Extract the key entities (people, places, things, "
                        "topics, preferences) from the user message. Reply "
                        "with ONLY a JSON array of strings, e.g. "
                        '["coffee", "Adithya"]. If none, reply [].'
                    ),
                },
                {"role": "user", "content": message},
            ],
            max_tokens=200,
            temperature=0.0,
        )
        parsed = _json_from(out)
        if isinstance(parsed, list):
            return [str(e) for e in parsed if str(e).strip()]
    except Exception:
        pass
    return []


def extract_facts(user_message, assistant_reply):
    """Return facts as [{subject, predicate, object, text}].

    predicate must be one of: LIKES, DISLIKES, KNOWS, WORKS_AT, PREFERS,
    INTERESTED_IN, OWNS, HAS_EVENT. subject is 'User' or a person's name.
    """
    try:
        out = _chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Extract durable facts about the USER from this "
                        "conversation turn. Reply with ONLY a JSON array of "
                        "objects: {subject, predicate, object, text}. "
                        "predicate must be one of: LIKES, DISLIKES, KNOWS, "
                        "WORKS_AT, PREFERS, INTERESTED_IN, OWNS, HAS_EVENT. "
                        "subject is 'User' or a person's name. text is a "
                        "one-sentence summary of the fact. Only include "
                        "facts the user stated or clearly confirmed. If "
                        "none, reply []."
                    ),
                },
                {
                    "role": "user",
                    "content": f"User: {user_message}\nAssistant: {assistant_reply}",
                },
            ],
            max_tokens=600,
            temperature=0.0,
        )
        parsed = _json_from(out)
        if isinstance(parsed, list):
            facts = []
            for f in parsed:
                if isinstance(f, dict) and f.get("predicate") and f.get("object"):
                    facts.append(
                        {
                            "subject": str(f.get("subject", "User")),
                            "predicate": str(f["predicate"]).upper(),
                            "object": str(f["object"]),
                            "text": str(f.get("text", "")) or f"{f.get('subject', 'User')} {f['predicate']} {f['object']}",
                        }
                    )
            return facts
    except Exception:
        pass
    return []


def reply_with_memories(user_message, memories):
    """Chat reply, grounded in the recalled memories (if any)."""
    memory_block = ""
    if memories:
        lines = [f"- {m}" for m in memories]
        memory_block = (
            "You have the following long-term memories about the user "
            "(from your FalkorDB graph memory). Use them when relevant, "
            "and briefly note when a memory informed your answer "
            "(e.g. 'I remember you like...').\n" + "\n".join(lines) + "\n\n"
        )
    system = (
        "You are ForgetMeNot, a friendly chat agent with long-term "
        "graph memory. You remember facts about the user across "
        "sessions. Be conversational and concise.\n"
        "IMPORTANT: Only state facts about the user that appear in the "
        "memories below. If no memory answers the question, say you "
        "don't remember — NEVER invent hobbies, jobs, names, or other "
        "personal facts about the user.\n" + memory_block
    )
    return _chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ],
        max_tokens=500,
        temperature=0.7,
    )
