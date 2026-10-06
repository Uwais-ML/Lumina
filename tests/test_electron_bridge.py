#!/usr/bin/env python3
"""
tests/test_electron_bridge.py — Automated integration tests for the Lumina bridge.

Tests: bridge startup, ping, model listing, tool listing, status, conversations,
       and streaming (connection error case). All tests run without a live model.

Run: python3 tests/test_electron_bridge.py
"""

import os
import sys
import json
import time
import subprocess

# ── Path setup ──────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_PACKAGES = os.path.join(
    PROJECT_ROOT, "python-dependencies", "macos-intel", "lib", "python3.12", "site-packages"
)
BRIDGE_PATH = os.path.join(PROJECT_ROOT, "app", "backend", "bridge.py")

env = os.environ.copy()
env["PYTHONPATH"] = ":".join([
    SITE_PACKAGES,
    os.path.join(PROJECT_ROOT, "scripts"),
    os.path.join(PROJECT_ROOT, "app", "backend"),
    os.path.join(PROJECT_ROOT, "Tools"),
    PROJECT_ROOT
])

# ── Test harness ────────────────────────────────────────────────────────────
PASS = "\033[32m✓ PASS\033[0m"
FAIL = "\033[31m✗ FAIL\033[0m"
results = []

def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    msg = f"  {status}  {name}"
    if detail and not condition:
        msg += f"\n         Detail: {detail}"
    print(msg)
    results.append((name, condition))
    return condition


def start_bridge(timeout=6):
    """Start the bridge subprocess and return (proc, ready_event)."""
    proc = subprocess.Popen(
        [sys.executable, BRIDGE_PATH],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=PROJECT_ROOT
    )
    ready_line = proc.stdout.readline()
    return proc, ready_line.strip()


def send(proc, payload):
    """Send a command and read the response line."""
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    return json.loads(line.strip()) if line.strip() else {}


def drain_stream(proc, req_id, max_events=20, timeout=6):
    """Collect stream events until message:complete or message:error."""
    events = []
    deadline = time.time() + timeout
    while time.time() < deadline and len(events) < max_events:
        line = proc.stdout.readline()
        if not line:
            break
        try:
            ev = json.loads(line.strip())
            events.append(ev)
            if ev.get("type") in ("message:complete", "message:error"):
                break
        except Exception:
            break
    return events


# ── Tests ────────────────────────────────────────────────────────────────────
def run_all_tests():
    print("\n" + "═" * 56)
    print("  Lumina Bridge — Automated Integration Tests")
    print("═" * 56 + "\n")

    proc, ready_raw = start_bridge()

    # ── 1. Bridge startup ──────────────────────────────────────────────────
    print("【1】 Bridge Startup")
    try:
        ready = json.loads(ready_raw) if ready_raw else {}
    except Exception:
        ready = {}

    check("bridge:ready event received",    bool(ready_raw), ready_raw)
    check("type == 'bridge:ready'",         ready.get("type") == "bridge:ready", str(ready))
    check("timestamp field present",        "timestamp" in ready)

    # ── 2. Ping ────────────────────────────────────────────────────────────
    print("\n【2】 Ping / Pong")
    r = send(proc, {"id": "ping1", "action": "ping"})
    check("response received",              bool(r))
    check("req_id matches",                 r.get("req_id") == "ping1", str(r))
    check("type == 'response'",             r.get("type") == "response", str(r))
    check("status == 'pong'",               r.get("data", {}).get("status") == "pong")
    check("port field is integer",          isinstance(r.get("data", {}).get("port"), int))

    # ── 3. Model listing ───────────────────────────────────────────────────
    print("\n【3】 Model Listing")
    r = send(proc, {"id": "ml1", "action": "list_models"})
    check("list_models response",           r.get("type") == "response", str(r))
    local = r.get("data", {}).get("local", [])
    check("local models is list",           isinstance(local, list))
    check("at least 1 GGUF model found",    len(local) >= 1, f"Found {len(local)}")
    if local:
        check("model has 'name' field",     "name" in local[0])
        check("model has 'size_mb' field",  "size_mb" in local[0])
        print(f"         Found models: {[m['name'] for m in local]}")

    # ── 4. Tool listing ────────────────────────────────────────────────────
    print("\n【4】 Tool Listing")
    r = send(proc, {"id": "tl1", "action": "list_tools"})
    check("list_tools response",            r.get("type") == "response")
    tools = r.get("data", [])
    check("tools is list",                  isinstance(tools, list))
    expected = {"code_and_run", "read_file", "save_file", "wiki_scrape", "pip_install"}
    found = {t["name"] for t in tools}
    check("core tools present",             expected.issubset(found), f"Got: {sorted(found)}")
    check("9 tools total",                  len(tools) == 9, f"Got {len(tools)}")

    # ── 5. Conversation list ───────────────────────────────────────────────
    print("\n【5】 Conversations")
    r = send(proc, {"id": "cv1", "action": "list_conversations"})
    check("list_conversations response",    r.get("type") == "response")
    check("data is list",                   isinstance(r.get("data"), list))

    # ── 6. Get status ──────────────────────────────────────────────────────
    print("\n【6】 System Status")
    r = send(proc, {"id": "st1", "action": "get_status"})
    check("get_status response",            r.get("type") == "response")
    sys_data = r.get("data", {}).get("system", {})
    check("ram_percent present",            "ram_percent" in sys_data, str(sys_data))
    check("cpu_percent present",            "cpu_percent" in sys_data)
    check("ram_percent in [0, 100]",        0 <= sys_data.get("ram_percent", -1) <= 100)
    print(f"         RAM: {sys_data.get('ram_percent', '?')}%  CPU: {sys_data.get('cpu_percent', '?')}%")

    # ── 7. Streaming — connection refused (no model) ───────────────────────
    print("\n【7】 Streaming (no model active — expect graceful error)")
    proc.stdin.write(json.dumps({
        "id": "cs1",
        "action": "chat_stream",
        "conversation_id": "test_conv_001",
        "messages": [{"role": "user", "content": "Hello Lumina"}],
        "mode": "chat",
        "model": "qwen"
    }) + "\n")
    proc.stdin.flush()

    events = drain_stream(proc, "cs1", max_events=10, timeout=8)
    types_seen = [e.get("type") for e in events]
    check("at least 1 stream event received",   len(events) >= 1, f"Got 0 events")
    check("message:start event fired",          "message:start" in types_seen, str(types_seen))
    terminated = "message:complete" in types_seen or "message:error" in types_seen
    check("stream terminated cleanly",          terminated, str(types_seen))
    all_have_req_id = all(e.get("req_id") == "cs1" for e in events)
    check("all events carry correct req_id",    all_have_req_id)
    print(f"         Event types: {types_seen}")

    # ── 8. Unknown action ──────────────────────────────────────────────────
    print("\n【8】 Unknown Action Handling")
    r = send(proc, {"id": "uk1", "action": "do_something_undefined"})
    check("error response for unknown action",  r.get("type") == "error", str(r))
    check("error message present",              bool(r.get("error")))

    # ── Cleanup ────────────────────────────────────────────────────────────
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        pass

    # ── Summary ────────────────────────────────────────────────────────────
    passed = sum(1 for _, ok in results if ok)
    failed = sum(1 for _, ok in results if not ok)
    total = len(results)

    print("\n" + "═" * 56)
    print(f"  Results:  {passed}/{total} passed", end="")
    if failed:
        print(f"   \033[31m{failed} FAILED\033[0m", end="")
    print()
    print("═" * 56 + "\n")

    if failed > 0:
        print("Failed tests:")
        for name, ok in results:
            if not ok:
                print(f"  ✗ {name}")
        print()
        sys.exit(1)
    else:
        print("  \033[32mAll tests passed! ✓\033[0m\n")
        sys.exit(0)


if __name__ == "__main__":
    run_all_tests()
