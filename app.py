import hmac, json, os, random, time
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, abort

app = Flask(__name__, static_folder=None)

PUBLIC_PAGES = {"index.html", "facilitator.html"}

# ── Facilitator auth ───────────────────────────────────────────────────────────
FACILITATOR_KEY = os.environ.get("FACILITATOR_KEY", "")
if not FACILITATOR_KEY:
    print("WARNING: FACILITATOR_KEY is not set - facilitator controls are open to anyone. "
          "Fine for local use, set it before running a real session.")

def facilitator_only(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if FACILITATOR_KEY:
            supplied = request.headers.get("X-Facilitator-Key", "")
            if not hmac.compare_digest(supplied.encode(), FACILITATOR_KEY.encode()):
                return jsonify({"error": "facilitator key required"}), 401
        return fn(*args, **kwargs)
    return wrapper

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
A participant described how they would dangerously cut corners in an AI security scenario, AND predicted what could go wrong.
Score BOTH parts and return ONLY valid JSON — no markdown, no explanation, just JSON.

Scenario: {situation}

Actual impact (ground truth): {actual_impact}

Participant's shortcut: {answer}

Participant's predicted impact: {predicted_impact}

Return this exact JSON structure:
{{
  "realism": <1-5 integer — how realistic is the shortcut>,
  "danger": <1-5 integer — how dangerous is the shortcut>,
  "creativity": <1-5 integer — how creative is the shortcut>,
  "impact_accuracy": <1-5 integer — how close is their predicted impact to the actual impact>,
  "impact_severity": <1-5 integer — did they grasp how severe the consequences could be>,
  "owasp": "<OWASP LLM category e.g. LLM01>",
  "shortcut_verdict": "<one witty sentence about their shortcut>",
  "impact_verdict": "<one witty sentence about their impact prediction>"
}}"""

def mock_score(answer: str, predicted_impact: str = "") -> dict:
    seed = sum(ord(c) for c in (answer + predicted_impact))
    rng = random.Random(seed)
    return {
        "realism":          rng.randint(2, 5),
        "danger":           rng.randint(2, 5),
        "creativity":       rng.randint(1, 5),
        "impact_accuracy":  rng.randint(1, 5),
        "impact_severity":  rng.randint(1, 5),
        "owasp":            "LLM01",
        "shortcut_verdict": "Bold move, cotton — let's see if it pays off. (mock score)",
        "impact_verdict":   "Your crystal ball needs calibration. (mock score)"
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

def ai_score(situation: str, answer: str, predicted_impact: str = "", actual_impact: str = "") -> dict:
    if not AZURE_ENDPOINT:
        return mock_score(answer, predicted_impact)
    try:
        prompt = SCORE_PROMPT.format(
            situation=situation, answer=answer,
            predicted_impact=predicted_impact, actual_impact=actual_impact
        )
        return _call_azure_openai(prompt)
    except Exception as e:
        print(f"AI scoring failed: {e}, using mock")
        return mock_score(answer, predicted_impact)

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
    predicted_impact = data.get("predicted_impact", "").strip()[:1000]
    idx     = state["current_idx"]

    if not nick or nick not in state["players"]:
        return jsonify({"error": "join first"}), 400
    if not answer:
        return jsonify({"error": "shortcut required"}), 400
    if not predicted_impact:
        return jsonify({"error": "predicted impact required"}), 400
    if idx is None:
        return jsonify({"error": "no active scenario"}), 400

    # prevent double-submit for same scenario
    player = state["players"][nick]
    if any(a["scenario_id"] == SCENARIOS[idx]["id"] for a in player["answers"]):
        return jsonify({"error": "already submitted"}), 400

    score_data = ai_score(
        SCENARIOS[idx]["situation"], answer,
        predicted_impact, SCENARIOS[idx]["impact"]
    )
    # Clamp all score fields to 1-5
    for key in ("realism", "danger", "creativity", "impact_accuracy", "impact_severity"):
        val = score_data.get(key, 0)
        if not isinstance(val, int):
            try: val = int(val)
            except: val = 0
        score_data[key] = max(0, min(5, val))
    total = (score_data["realism"] + score_data["danger"] +
             score_data["creativity"] + score_data["impact_accuracy"] +
             score_data["impact_severity"])
    player["score"] += total
    player["answers"].append({
        "scenario_id": SCENARIOS[idx]["id"],
        "answer": answer,
        "predicted_impact": predicted_impact,
        "score": score_data,
        "total": total,
        "ts": time.time()
    })
    return jsonify({
        "ok": True, "score": score_data, "total": total,
        "situation": SCENARIOS[idx]["situation"],
        "answer": answer,
        "predicted_impact": predicted_impact,
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
@facilitator_only
def answers():
    """Facilitator: answers for a specific or current scenario, or all."""
    scope = request.args.get("scope", "current")  # current | all | <scenario_id>
    if scope == "all":
        result = []
        for nick, p in state["players"].items():
            for a in p["answers"]:
                result.append({"nickname": nick, **a})
        result.sort(key=lambda x: x["ts"])
        return jsonify({"answers": result})
    elif scope == "current":
        idx = state["current_idx"]
        if idx is None:
            return jsonify({"answers": []})
        sid = SCENARIOS[idx]["id"]
    else:
        try: sid = int(scope)
        except: return jsonify({"error": "invalid scope"}), 400
    result = []
    for nick, p in state["players"].items():
        for a in p["answers"]:
            if a["scenario_id"] == sid:
                result.append({"nickname": nick, **a})
    result.sort(key=lambda x: -x["total"])
    return jsonify({"answers": result})

@app.route("/api/next", methods=["POST"])
@facilitator_only
def next_scenario():
    idx = state["current_idx"]
    if idx is None:
        state["current_idx"] = 0
    elif idx + 1 < len(SCENARIOS):
        state["current_idx"] = idx + 1
    else:
        state["current_idx"] = None  # back to lobby / done
    state["revealed"] = False
    state["timer_start"] = None
    return jsonify({"ok": True, "current_idx": state["current_idx"]})

@app.route("/api/start_timer", methods=["POST"])
@facilitator_only
def start_timer():
    if state["current_idx"] is not None:
        state["timer_start"] = time.time()
    return jsonify({"ok": True})

@app.route("/api/reveal", methods=["POST"])
@facilitator_only
def reveal():
    state["revealed"] = True
    return jsonify({"ok": True})

@app.route("/api/reset", methods=["POST"])
@facilitator_only
def reset():
    state["players"] = {}
    state["current_idx"] = None
    state["revealed"] = False
    state["timer_start"] = None
    return jsonify({"ok": True})

@app.route("/api/set_scenario", methods=["POST"])
@facilitator_only
def set_scenario():
    data = request.json or {}
    idx = data.get("index")
    if idx is not None and 0 <= idx < len(SCENARIOS):
        state["current_idx"] = idx
        state["revealed"] = False
        state["timer_start"] = None
    return jsonify({"ok": True, "current_idx": state["current_idx"]})

@app.route("/api/players", methods=["GET"])
@facilitator_only
def players():
    """List all players with per-question score breakdown."""
    idx = state["current_idx"]
    sid = SCENARIOS[idx]["id"] if idx is not None else None
    result = []
    for nick, p in state["players"].items():
        submitted = any(a["scenario_id"] == sid for a in p["answers"]) if sid else False
        # Per-question breakdown
        breakdown = []
        for a in p["answers"]:
            breakdown.append({
                "scenario_id": a["scenario_id"],
                "total": a["total"],
                "scores": {k: a["score"][k] for k in ("realism","danger","creativity","impact_accuracy","impact_severity") if k in a["score"]}
            })
        result.append({
            "nickname": nick,
            "total_score": p["score"],
            "submitted": submitted,
            "breakdown": breakdown
        })
    result.sort(key=lambda x: -x["total_score"])
    return jsonify({"players": result})

@app.route("/api/scenarios_list", methods=["GET"])
@facilitator_only
def scenarios_list():
    return jsonify({"scenarios": SCENARIOS, "current_idx": state["current_idx"], "timer_start": state["timer_start"]})

@app.route("/", defaults={"path": "index.html"})
@app.route("/<path:path>")
def static_files(path):
    # Only serve the two UI pages; everything else (scenarios.json, app.py, .env) stays private.
    if path not in PUBLIC_PAGES:
        abort(404)
    return send_from_directory(".", path)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
