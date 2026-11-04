import os
import time
from dotenv import load_dotenv

load_dotenv()

import boto3
from botocore.config import Config
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from google import genai
from google.genai import types

from tools.label import get_drug_label
from tools.adverse_events import get_adverse_events
from tools.recalls import get_drug_recalls
from tools.approvals import get_drug_approvals
from tools.interactions import get_drug_interactions
from tools.label_search import search_label_passages, _warm_up

app = Flask(__name__)
CORS(app)

_client = None
_chat = None

# Alert email settings (set these as Cloud Run environment variables / secrets):
#   ALERT_EMAIL            verified SES address, used as both sender and recipient
#   AWS_REGION             defaults to us-east-1
#   AWS_ACCESS_KEY_ID      boto3 reads these two automatically
#   AWS_SECRET_ACCESS_KEY
ALERT_EMAIL = os.environ.get("ALERT_EMAIL")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
# Comma-separated IPs that should NOT trigger an alert email (your own IPs).
IGNORE_IPS = {ip.strip() for ip in os.environ.get("IGNORE_IPS", "").split(",") if ip.strip()}
_ses = None

SYSTEM_INSTRUCTION = (
    "You are an FDA drug information assistant. "
    "For any question that names a drug, you must use your tools and never answer from memory. "
    "Pick only the tool or tools the question actually needs: "
    "labels for uses, dosage and warnings; adverse events for reported side effects; "
    "recalls for recall history; approvals for approval dates, makers and marketing status; "
    "label passage search for open-ended questions about what a drug label says, such as "
    "food, alcohol, pregnancy or other specific situations. "
    "Base your answer only on what the tools return. If a tool finds nothing, say so plainly. "
    "Give a complete answer in 3 to 5 sentences of plain prose, without markdown. "
    "Remind the user this is not medical advice when you give dosage or safety information."
)

import functools

_warm_up()

CALL_LOG = []

def logged(fn):
    """Wrap a tool so each call and its result are recorded."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        entry = {"tool": fn.__name__, "args": kwargs or {"args": list(args)}}
        CALL_LOG.append(entry)
        t0 = time.time()
        result = fn(*args, **kwargs)
        print(f"TIMING tool {fn.__name__} took {time.time() - t0:.2f}s", flush=True)
        entry["result"] = result
        return result
    return wrapper

TOOLS = [logged(get_drug_label), logged(get_adverse_events), logged(get_drug_recalls), logged(get_drug_approvals), logged(get_drug_interactions), logged(search_label_passages)]

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


def get_ses():
    global _ses
    if _ses is None:
        _ses = boto3.client(
            "ses",
            region_name=AWS_REGION,
            # Short timeouts so a slow SES call can never hang the chat.
            config=Config(connect_timeout=3, read_timeout=3, retries={"max_attempts": 1}),
        )
    return _ses


def client_ip():
    """Visitor's real IP. On Cloud Run it arrives in X-Forwarded-For
    (first entry is the client), not in request.remote_addr."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or ""


def send_alert_email(drug, question, trail, status="ok"):
    """Email Ray the drug, the question and the tools Gemini chose.
    Skips requests from IGNORE_IPS. Never raises: a failed email
    must not break the chat."""
    if not ALERT_EMAIL:
        return
    try:
        ip = client_ip()
        if ip in IGNORE_IPS:
            return
        tool_lines = [f"- {t['tool']}({t.get('args', {})})" for t in trail]
        tools_text = "\n".join(tool_lines) if tool_lines else "(none)"
        body = (
            f"Drug: {drug or '(not set)'}\n"
            f"Question: {question}\n"
            f"Status: {status}\n"
            f"IP: {ip}\n"
            f"Tools used:\n{tools_text}\n"
        )
        subject = f"FDA app: {drug or question}"
        subject = " ".join(subject.split())[:120]  # one line, trimmed
        get_ses().send_email(
            Source=ALERT_EMAIL,
            Destination={"ToAddresses": [ALERT_EMAIL]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
            },
        )
    except Exception as e:
        print(f"alert email failed: {e}", flush=True)


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
    question = message          # keep the user's original wording for the email
    drug = body.get("drug")
    try:
        CALL_LOG.clear()
        global _chat
        _chat = None
        if drug:
            message = (f"(Drug under discussion: {drug}. If this question is a "
            f"follow-up without a drug name, it refers to this drug.)\n{message}")
        t0 = time.time()
        response = get_chat().send_message(message)
        print(f"TIMING send_message total took {time.time() - t0:.2f}s", flush=True)
        trail = list(CALL_LOG)
        t1 = time.time()
        send_alert_email(drug, question, trail)
        print(f"TIMING alert email took {time.time() - t1:.2f}s", flush=True)
        return jsonify(reply=response.text, trail=trail)
    except Exception as e:
        msg = str(e)
        trail = list(CALL_LOG)
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            send_alert_email(drug, question, trail, status="rate limited (429)")
            return jsonify(
                reply="The AI is getting a lot of requests right now. Please wait a minute and try again.",
                trail=trail,
            ), 429
        send_alert_email(drug, question, trail, status="error")
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
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
