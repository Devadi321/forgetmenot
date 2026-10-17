"""ForgetMeNot — Flask web app + chat API."""
import os

from flask import Flask, jsonify, render_template, request

from llm import extract_entities, extract_facts, reply_with_memories
from memory import Memory

app = Flask(__name__)
mem = Memory()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "empty message"}), 400

    # --- commands -----------------------------------------------------------
    if message.startswith("/"):
        parts = message.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""
        if cmd == "/help":
            return jsonify(
                {
                    "reply": (
                        "Commands:\n"
                        "/memories — list everything I remember\n"
                        "/forget <thing> — delete memories about it\n"
                        "/graph — show the memory graph\n"
                        "/reset — wipe all memories\n"
                        "/help — this list"
                    ),
                    "command": "help",
                }
            )
        if cmd == "/memories":
            memories = mem.list_memories()
            if not memories:
                reply = "I don't remember anything yet. Tell me something about yourself!"
            else:
                reply = "Here's what I remember:\n" + "\n".join(
                    f"- [{m['rel']}] {m['text']}" for m in memories
                )
            return jsonify({"reply": reply, "command": "memories", "memories": memories})
        if cmd == "/forget":
            if not arg:
                return jsonify(
                    {"reply": "Usage: /forget <thing> — e.g. /forget coffee"}
                )
            deleted = mem.forget(arg)
            return jsonify(
                {
                    "reply": f"Forgot {deleted} memor{'y' if deleted == 1 else 'ies'} about '{arg}'.",
                    "command": "forget",
                    "deleted": deleted,
                }
            )
        if cmd == "/graph":
            return jsonify(
                {"reply": "Here's your memory graph.", "command": "graph", "graph": mem.get_graph()}
            )
        if cmd == "/reset":
            mem.clear()
            mem.ensure_user()
            return jsonify({"reply": "All memories wiped. Fresh start.", "command": "reset"})
        return jsonify({"reply": f"Unknown command '{cmd}'. Try /help."})

    # --- normal chat: recall -> reply -> remember ----------------------------
    mem.ensure_user()
    entities = extract_entities(message)
    memories = mem.recall(entities)
    reply = reply_with_memories(message, memories)
    facts = extract_facts(message, reply)
    mem.write_facts(facts)
    return jsonify(
        {
            "reply": reply,
            "entities": entities,
            "memories_used": memories,
            "facts_saved": [f["text"] for f in facts],
        }
    )


@app.route("/api/memories")
def memories():
    return jsonify({"memories": mem.list_memories()})


@app.route("/api/graph")
def graph():
    return jsonify(mem.get_graph())


@app.route("/api/reset", methods=["POST"])
def reset():
    mem.clear()
    mem.ensure_user()
    return jsonify({"ok": True})


if __name__ == "__main__":
    mem.ensure_user()
    port = int(os.environ.get("PORT", "5058"))
    app.run(host="0.0.0.0", port=port, debug=True)
