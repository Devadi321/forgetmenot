# ForgetMeNot — 2-minute demo script

Record your screen with the app open at http://localhost:5058.
**Before recording:** click `/reset` in the chat so the graph starts empty
(the video is cleaner if the agent learns everything on camera).
Speak the lines in *italics* as voiceover, or add them as captions.

---

**[0:00–0:15] Intro — show the empty app**
> *"This is ForgetMeNot — a chat agent whose memory lives in a FalkorDB
> graph, not in the chat history. Right now it knows nothing about me."*
- Show the empty chat + empty memory panel.

**[0:15–0:40] Teach it facts**
Type:
> `Hi, my name is Adithya and I love coffee. I work at Coupamini.`
> *"It replies using what I just said — and look: it saved two facts to
> the graph."*
- Point at the "💾 Saved:" line under the reply and the memory panel
  (Preference: coffee, Topic: Coupamini, Fact nodes).

**[0:40–1:00] Prove memory survives a new session**
Click **🔄 New session**.
> *"New session — the chat is wiped. But memory lives in FalkorDB, not
> here."*
Type:
> `What do I like and where do I work?`
> *"It recalls both facts via graph traversal — two hops from the
> matched entities."*
- Point at the "🧠 Recalled:" line.

**[1:00–1:25] Show the graph**
Type `/memories`, then `/graph`.
> *"Every memory is a real node with a typed relationship — LIKES,
> WORKS_AT, REMEMBER. This is the graph, not a JSON file."*
- Show the memory-graph panel (nodes + edges).

**[1:25–1:50] Forget — and prove it really forgot**
Type:
> `/forget coffee`
> *"Two coffee memories deleted — nodes and edges, gone."*
Type:
> `What do I like?`
> *"It says it doesn't remember — it never invents facts. That's the
> whole point: memory you can trust and erase."*

**[1:50–2:00] Outro**
> *"ForgetMeNot — agent memory as a graph, built on FalkorDB. It never
> forgets… until you tell it to."*
- End on the app + the `/graph` view.

---

## If something goes wrong on camera

- **Reply is slow:** the free Pollinations API can take 10–20s per
  message (3 LLM calls per turn). Just wait — or cut the pause in editing.
- **A fact isn't extracted:** rephrase plainly, e.g. `I like tea.`
- **Want to re-take from scratch:** type `/reset`, then start again at 0:15.
