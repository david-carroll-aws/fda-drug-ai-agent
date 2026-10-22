from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from google import genai
from google.genai import types

from tools.label import get_drug_label
from tools.adverse_events import get_adverse_events
from tools.recalls import get_drug_recalls
from tools.approvals import get_drug_approvals
from tools.interactions import get_drug_interactions

app = Flask(__name__)
CORS(app)

_client = None
_chat = None

SYSTEM_INSTRUCTION = (
    "You are an FDA drug information assistant. "
    "For any question that names a drug, you must use your tools and never answer from memory. "
    "Pick only the tool or tools the question actually needs: "
    "labels for uses, dosage and warnings; adverse events for reported side effects; "
    "recalls for recall history; approvals for approval dates, makers and marketing status. "
    "Base your answer only on what the tools return. If a tool finds nothing, say so plainly. "
    "Give a complete answer in 3 to 5 sentences of plain prose, without markdown. "
    "Remind the user this is not medical advice when you give dosage or safety information."
)

import functools

CALL_LOG = []

def logged(fn):
    """Wrap a tool so each call and its result are recorded."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        entry = {"tool": fn.__name__, "args": kwargs or {"args": list(args)}}
        CALL_LOG.append(entry)
        result = fn(*args, **kwargs)
        entry["result"] = result
        return result
    return wrapper

TOOLS = [logged(get_drug_label), logged(get_adverse_events), logged(get_drug_recalls), logged(get_drug_approvals), logged(get_drug_interactions)]

def get_client():
    global _client
    if _client is None:
        _client = genai.Client(
            vertexai=True,
            project="dacnyc-chainlink-nodes",
            location="global"
        )
    return _client


def get_chat():
    global _chat
    if _chat is None:
        _chat = get_client().chats.create(
            model="gemini-3.1-flash-lite",
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                tools=TOOLS,
                max_output_tokens=800,
                thinking_config=types.ThinkingConfig(thinking_level="low")
            )
        )
    return _chat


def tool_trail(response):
    """Pull out which tools the model called and with what arguments."""
    trail = []
    for content in getattr(response, "automatic_function_calling_history", None) or []:
        for part in content.parts or []:
            if part.function_call:
                trail.append({
                    "tool": part.function_call.name,
                    "args": dict(part.function_call.args or {}),
                })
    return trail


@app.get("/")
def index():
    return send_file("index.html")


@app.post("/chat")
def chat_endpoint():
    body = request.json or {}
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify(error="empty message"), 400
    try:
        CALL_LOG.clear()
        global _chat
        _chat = None
        drug = request.json.get("drug")
        if drug:
            message = (f"(Drug under discussion: {drug}. If this question is a "
            f"follow-up without a drug name, it refers to this drug.)\n{message}")
        response = get_chat().send_message(message)
        return jsonify(reply=response.text, trail=list(CALL_LOG))
    except Exception as e:
        msg = str(e)
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            return jsonify(
                reply="The AI is getting a lot of requests right now. Please wait a minute and try again.",
                trail=list(CALL_LOG),
            ), 429
        return jsonify(error="Something went wrong. Please try again."), 500


@app.get("/models")
def list_models():
    """Return available Gemini models from Vertex AI."""
    try:
        client = get_client()
        models = []

        for m in client.models.list():
            name = getattr(m, "name", "") or ""
            short_name = name.split("/")[-1] if "/" in name else name

            models.append({
                "name": short_name,
                "displayName": getattr(m, "display_name", None) or short_name,
                "description": getattr(m, "description", None) or "",
                "inputTokenLimit": getattr(m, "input_token_limit", None),
                "outputTokenLimit": getattr(m, "output_token_limit", None),
                "supportedActions": getattr(m, "supported_actions", None) or [],
            })

        gemini_models = [
            m for m in models
            if "gemini" in m["name"].lower()
        ]
        gemini_models.sort(key=lambda m: m["name"])

        return jsonify(models=gemini_models, count=len(gemini_models))

    except Exception as e:
        return jsonify(error=str(e)), 500


if __name__ == "__main__":
    app.run(port=5000)