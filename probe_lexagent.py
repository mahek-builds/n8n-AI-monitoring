"""
LexAgent Synthetic Probe & Validation Utility
Simulates the n8n AI monitoring pipeline against the LexAgent API.
"""

import argparse
import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone


def run_probe(base_url="http://localhost:8000", simulate_invalid_path=False):
    run_id = f"run_{int(time.time()):x}_{int(time.time() * 1000) % 10000:04x}"
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    project = "LexAgent"
    endpoint_label = "POST /research"

    config = {
        "run_id": run_id,
        "timestamp": timestamp,
        "project": project,
        "endpoint_label": endpoint_label,
        "configured": True,
        "method": "POST",
        "url": f"{base_url}/research",
        "body": {
            "session_id": "probe-smoke",
            "question": "Define breach of contract in one short paragraph.",
            "document_ids": [],
        },
        "answer_path": "nonexistent" if simulate_invalid_path else "answer.summary",
        "min_answer_len": 40,
        "must_contain": "contract",
        "citations_path": "answer.sources",
        "citations_required": False,
        "sources_path": "",
        "usage": {"input": "", "output": "", "total": "", "model": ""},
    }

    out = {
        "run_id": config["run_id"],
        "timestamp": config["timestamp"],
        "project": config["project"],
        "endpoint_label": config["endpoint_label"],
        "http_status": "",
        "latency_ms": "",
        "validation_status": "FAIL",
        "error_summary": "",
        "input_tokens": "",
        "output_tokens": "",
        "total_tokens": "",
        "model": "",
        "estimated_cost": "",
        "notes": "",
        "attempt": 0,
        "transient": False,
    }

    print(f"[*] Dispatching probe to {config['url']}...")
    start_time = time.time()

    def get_path(obj, path):
        if not path:
            return None
        parts = path.split(".")
        current = obj
        for p in parts:
            if current is None or not isinstance(current, dict):
                return None
            current = current.get(p)
        return current

    try:
        data = json.dumps(config["body"]).encode("utf-8")
        req = urllib.request.Request(
            config["url"], data=data, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            status_code = resp.status
            body_bytes = resp.read()
            body = json.loads(body_bytes.decode("utf-8"))
    except urllib.error.HTTPError as e:
        status_code = e.code
        body_bytes = e.read()
        try:
            body = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            body = body_bytes.decode("utf-8", errors="ignore")
    except Exception as e:
        latency = int((time.time() - start_time) * 1000)
        out["latency_ms"] = latency
        out["http_status"] = 0
        out["transient"] = True
        out["error_summary"] = str(e)[:200]
        return out

    latency = int((time.time() - start_time) * 1000)
    out["latency_ms"] = latency
    out["http_status"] = status_code

    if status_code < 200 or status_code >= 300:
        out["transient"] = status_code in (502, 503, 504)
        out["error_summary"] = f"HTTP {status_code} {json.dumps(body)}"[:200]
        return out

    answer = get_path(body, config["answer_path"]) if config["answer_path"] else body
    if not isinstance(answer, str) or len(answer.strip()) < config["min_answer_len"]:
        out["error_summary"] = f"HTTP 200 but {config['answer_path']} missing or empty"
        return out

    if (
        config["must_contain"]
        and config["must_contain"].lower() not in answer.lower()
    ):
        out["error_summary"] = "Expected keyword not found in answer"
        return out

    notes = []
    if config["citations_path"]:
        sources = get_path(body, config["citations_path"])
        has_citations = (
            len(sources) > 0
            if isinstance(sources, list)
            else bool(sources)
        )
        if not has_citations and config["citations_required"]:
            out["error_summary"] = "Citation field empty"
            return out
        notes.append(
            "citation field present (presence only, not accuracy)"
            if has_citations
            else "citation field empty"
        )

    out["notes"] = "; ".join(notes)
    out["validation_status"] = "PASS"
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Probe LexAgent API")
    parser.add_argument(
        "--url", default="http://localhost:8000", help="Base URL of LexAgent API"
    )
    parser.add_argument(
        "--fail", action="store_true", help="Simulate invalid answer_path failure"
    )
    args = parser.parse_args()

    result = run_probe(base_url=args.url, simulate_invalid_path=args.fail)
    print("\n--- PROBE EXECUTION RESULT ---")
    for k, v in result.items():
        print(f"  {k:18}: {v}")
