import json, os, random, time
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder=".")

# ── State ──────────────────────────────────────────────────────────────────────
with open("scenarios.json", encoding="utf-8") as f:
    SCENARIOS = json.load(f)

state = {
    "players": {},          # nickname -> {score, answers:[]}
    "current_idx": None,    # index into SCENARIOS, None = lobby
    "revealed": False,
    "timer_start": None,    # epoch when current scenario started
}

# ── Azure OpenAI scoring ───────────────────────────────────────────────────────
AZURE_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
AZURE_DEPLOY   = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")

SCORE_PROMPT = """You are the ruthless judge of "Cutting Corners Hero", a security awareness game.
A participant described how they would dangerously cut corners in an AI security scenario.
Score their answer and return ONLY valid JSON — no markdown, no explanation, just JSON.

Scenario: {situation}

Participant answer: {answer}

Return this exact JSON structure:
{{
  "realism": <1-5 integer>,
  "danger": <1-5 integer>,
  "creativity": <1-5 integer>,
  "owasp": "<OWASP LLM category e.g. LLM01>",
  "verdict": "<one witty sentence praising their recklessness>"
}}"""

def mock_score(answer: str) -> dict:
    seed = sum(ord(c) for c in answer)
    rng = random.Random(seed)
    return {
        "realism":    rng.randint(2, 5),
        "danger":     rng.randint(2, 5),
        "creativity": rng.randint(1, 5),
        "owasp":      "LLM01",
        "verdict":    "Bold move, cotton — let's see if it pays off. (mock score)"
    }

def _get_azure_token() -> str:
    from azure.identity import DefaultAzureCredential
    credential = DefaultAzureCredential()
    token = credential.get_token("https://cognitiveservices.azure.com/.default")
    return token.token

def _call_azure_openai(prompt: str) -> dict:
    import httpx
    token = _get_azure_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 200
    }
    url = f"{AZURE_ENDPOINT}/openai/deployments/{AZURE_DEPLOY}/chat/completions?api-version=2024-02-01"
    r = httpx.post(url, json=payload, headers=headers, timeout=15)
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"].strip())

def ai_score(situation: str, answer: str) -> dict:
    if not AZURE_ENDPOINT:
        return mock_score(answer)
    try:
        prompt = SCORE_PROMPT.format(situation=situation, answer=answer)
        return _call_azure_openai(prompt)
    except Exception as e:
        print(f"AI scoring failed: {e}, using mock")
        return mock_score(answer)

# ── API ────────────────────────────────────────────────────────────────────────
@app.route("/api/join", methods=["POST"])
def join():
    nick = request.json.get("nickname", "").strip()[:30]
    if not nick:
        return jsonify({"error": "nickname required"}), 400
    if nick not in state["players"]:
        state["players"][nick] = {"score": 0, "answers": []}
    return jsonify({"ok": True, "nickname": nick})

@app.route("/api/scenario", methods=["GET"])
def get_scenario():
    idx = state["current_idx"]
    if idx is None:
        return jsonify({"status": "lobby"})
    s = SCENARIOS[idx]
    resp = {
        "status": "active",
        "revealed": state["revealed"],
        "scenario": {
            "id": s["id"],
            "trap": s["trap"],
            "situation": s["situation"],
            "index": idx,
            "total": len(SCENARIOS)
        }
    }
    if state["timer_start"]:
        resp["timer_start"] = state["timer_start"]
    if state["revealed"]:
        resp["scenario"]["impact"]     = s["impact"]
        resp["scenario"]["mitigation"] = s["mitigation"]
        resp["scenario"]["owasp"]      = s["owasp"]
    return jsonify(resp)

@app.route("/api/submit", methods=["POST"])
def submit():
    data    = request.json or {}
    nick    = data.get("nickname", "").strip()
    answer  = data.get("answer", "").strip()[:1000]
    idx     = state["current_idx"]

    if not nick or nick not in state["players"]:
        return jsonify({"error": "join first"}), 400
    if not answer:
        return jsonify({"error": "answer required"}), 400
    if idx is None:
        return jsonify({"error": "no active scenario"}), 400

    # prevent double-submit for same scenario
    player = state["players"][nick]
    if any(a["scenario_id"] == SCENARIOS[idx]["id"] for a in player["answers"]):
        return jsonify({"error": "already submitted"}), 400

    score_data = ai_score(SCENARIOS[idx]["situation"], answer)
    total = score_data.get("realism",0) + score_data.get("danger",0) + score_data.get("creativity",0)
    player["score"] += total
    player["answers"].append({
        "scenario_id": SCENARIOS[idx]["id"],
        "answer": answer,
        "score": score_data,
        "total": total,
        "ts": time.time()
    })
    return jsonify({
        "ok": True, "score": score_data, "total": total,
        "situation": SCENARIOS[idx]["situation"],
        "answer": answer,
        "impact": SCENARIOS[idx]["impact"],
        "mitigation": SCENARIOS[idx]["mitigation"],
    })

@app.route("/api/leaderboard", methods=["GET"])
def leaderboard():
    board = sorted(
        [{"nickname": k, "score": v["score"]} for k, v in state["players"].items()],
        key=lambda x: -x["score"]
    )[:10]
    return jsonify({"leaderboard": board})

@app.route("/api/answers", methods=["GET"])
def answers():
    """Facilitator: all answers for current scenario"""
    idx = state["current_idx"]
    if idx is None:
        return jsonify({"answers": []})
    sid = SCENARIOS[idx]["id"]
    result = []
    for nick, p in state["players"].items():
        for a in p["answers"]:
            if a["scenario_id"] == sid:
                result.append({"nickname": nick, **a})
    result.sort(key=lambda x: x["ts"])
    return jsonify({"answers": result})

@app.route("/api/next", methods=["POST"])
def next_scenario():
    idx = state["current_idx"]
    if idx is None:
        state["current_idx"] = 0
    elif idx + 1 < len(SCENARIOS):
        state["current_idx"] = idx + 1
    else:
        state["current_idx"] = None  # back to lobby / done
    state["revealed"] = False
    state["timer_start"] = time.time() if state["current_idx"] is not None else None
    return jsonify({"ok": True, "current_idx": state["current_idx"]})

@app.route("/api/reveal", methods=["POST"])
def reveal():
    state["revealed"] = True
    return jsonify({"ok": True})

@app.route("/api/players", methods=["GET"])
def players():
    """List all registered players and whether they've submitted for the current scenario."""
    idx = state["current_idx"]
    sid = SCENARIOS[idx]["id"] if idx is not None else None
    result = []
    for nick, p in state["players"].items():
        submitted = any(a["scenario_id"] == sid for a in p["answers"]) if sid else False
        result.append({"nickname": nick, "submitted": submitted})
    return jsonify({"players": result})

@app.route("/api/scenarios_list", methods=["GET"])
def scenarios_list():
    return jsonify({"scenarios": SCENARIOS, "current_idx": state["current_idx"], "timer_start": state["timer_start"]})

@app.route("/", defaults={"path": "index.html"})
@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(".", path)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
