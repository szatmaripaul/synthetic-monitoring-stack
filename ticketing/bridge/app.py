import os
import yaml
import requests
from flask import Flask, request, jsonify
from string import Template

app = Flask(__name__)

ALERTA_BASE_URL = os.getenv("ALERTA_BASE_URL", "http://alerta:8080")
ZAMMAD_BASE_URL = os.getenv("ZAMMAD_BASE_URL", "")
ZAMMAD_TOKEN = os.getenv("ZAMMAD_TOKEN", "")
ZAMMAD_CUSTOMER_EMAIL = os.getenv("ZAMMAD_CUSTOMER_EMAIL", "monitoring@local")
BRIDGE_CONFIG = os.getenv("BRIDGE_CONFIG", "/app/config.yml")

with open(BRIDGE_CONFIG, "r", encoding="utf-8") as f:
    CFG = yaml.safe_load(f)

def render_template(path, data):
    with open(path, "r", encoding="utf-8") as f:
        tpl = Template(f.read().replace("{{", "${").replace("}}", "}"))
    return tpl.safe_substitute(**data)

def zammad_headers():
    return {
        "Authorization": f"Token token={ZAMMAD_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

def pick_group(payload):
    team = (
        (payload.get("attributes") or {}).get("team")
        or (payload.get("tags") or {}).get("team")
    )
    if team:
        return CFG.get("team_group_map", {}).get(
            str(team).lower(),
            CFG.get("default_group", "Users"),
        )
    return CFG.get("default_group", "Users")

def pick_priority(severity):
    sev = (severity or "").lower()
    return CFG.get("severity_map", {}).get(
        sev,
        {"priority": CFG.get("default_priority", "2 normal")},
    )["priority"]

@app.post("/webhook/alerta")
def alerta_webhook():
    payload = request.json or {}

    status = payload.get("status", "unknown")
    severity = payload.get("severity", "minor")
    event = payload.get("event", "alert")
    resource = payload.get("resource", "unknown")
    environment = payload.get("environment", "unknown")
    text = payload.get("text", "") or payload.get("summary", "")
    service = payload.get("service", ["unknown"])
    if isinstance(service, list):
        service = ",".join(service)

    key = payload.get("id", f"{environment}:{resource}:{event}")

    body = render_template(
        "/app/templates/ticket.md",
        {
            "status": status,
            "severity": severity,
            "event": event,
            "resource": resource,
            "environment": environment,
            "text": text,
            "service": service,
            "key": key,
        },
    )

    title = f"[{severity.upper()}] {environment} {service} {event} on {resource}"

    if not ZAMMAD_TOKEN:
        return jsonify({"error": "ZAMMAD_TOKEN not set"}), 500

    ticket_payload = {
        "title": title,
        "group": pick_group(payload),
        "priority": pick_priority(severity),
        "customer": ZAMMAD_CUSTOMER_EMAIL,
        "article": {
            "subject": title,
            "body": body,
            "type": "note",
            "internal": False,
        },
    }

    r = requests.post(
        f"{ZAMMAD_BASE_URL}/api/v1/tickets",
        headers=zammad_headers(),
        json=ticket_payload,
        timeout=15,
    )

    if r.status_code >= 300:
        return jsonify(
            {"error": "ticket_create_failed", "status": r.status_code, "body": r.text}
        ), 502

    return jsonify({"ok": True, "ticket": r.json(), "key": key})

@app.get("/health")
def health():
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
