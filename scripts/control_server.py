#!/usr/bin/env python3
"""
Lumina Control Centre Server
Serves the Control Centre HTML and provides a REST API to execute Lumina commands.
Usage: python3 scripts/control_server.py [--port PORT]
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUMINA_PY    = os.path.join(PROJECT_ROOT, "Lumina.py")
MODELS_DIR   = os.path.join(PROJECT_ROOT, "models")
LOGS_DIR     = os.path.join(PROJECT_ROOT, "logs")
DATA_DIR     = os.path.join(PROJECT_ROOT, "data")
HTML_PATH    = os.path.join(PROJECT_ROOT, "resources", "web", "control_centre.html")

# Bundled Python path (prefer 3.12 for RAG, fallback 3.10)
def bundled_python():
    for v in ("3.12", "3.10"):
        p = os.path.join(PROJECT_ROOT, "python-dependencies", "macos-intel", "bin", f"python{v}")
        if os.path.isfile(p):
            return p
    return sys.executable

# Active process store: { job_id -> { proc, log_lines, status } }
_jobs = {}
_jobs_lock = threading.Lock()


def local_models():
    files = glob.glob(os.path.join(MODELS_DIR, "*.gguf"))
    return [os.path.basename(f) for f in sorted(files)]


def active_model_status():
    status_file = os.path.join(DATA_DIR, "status.txt")
    try:
        with open(status_file) as f:
            return json.load(f)
    except Exception:
        return {}


def get_env():
    env = os.environ.copy()
    for v in ("3.12", "3.10"):
        sp = os.path.join(PROJECT_ROOT, "python-dependencies", "macos-intel", "lib", f"python{v}", "site-packages")
        if os.path.isdir(sp):
            env["PYTHONPATH"] = sp
            break
    return env


def run_job(job_id, cmd):
    with _jobs_lock:
        _jobs[job_id] = {"status": "running", "lines": [], "started": time.time()}

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=PROJECT_ROOT,
            env=get_env(),
        )
        with _jobs_lock:
            _jobs[job_id]["pid"] = proc.pid

        for line in proc.stdout:
            with _jobs_lock:
                _jobs[job_id]["lines"].append(line.rstrip())
                # Keep last 500 lines only
                if len(_jobs[job_id]["lines"]) > 500:
                    _jobs[job_id]["lines"] = _jobs[job_id]["lines"][-500:]

        rc = proc.wait()
        with _jobs_lock:
            _jobs[job_id]["status"] = "done" if rc == 0 else "error"
            _jobs[job_id]["exit_code"] = rc

    except Exception as e:
        with _jobs_lock:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["lines"].append(f"[!] Failed to start: {e}")


class ControlHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # Suppress default access log

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, path):
        try:
            with open(path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except FileNotFoundError:
            self.send_error(404, "Not found")

    def do_HEAD(self):
        self.do_GET()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path

        if path in ("/", "/index.html"):
            self.send_html(HTML_PATH)

        elif path == "/api/models":
            self.send_json({"models": local_models()})

        elif path == "/api/status":
            self.send_json(active_model_status())

        elif path.startswith("/api/job/"):
            job_id = path.split("/api/job/")[-1]
            with _jobs_lock:
                job = _jobs.get(job_id)
            if job is None:
                self.send_json({"error": "Job not found"}, 404)
            else:
                qs    = parse_qs(parsed.query)
                since = int(qs.get("since", ["0"])[0])
                lines = job["lines"][since:]
                self.send_json({
                    "status":    job["status"],
                    "lines":     lines,
                    "total":     len(job["lines"]),
                    "exit_code": job.get("exit_code"),
                })

        elif path == "/api/jobs":
            with _jobs_lock:
                summary = {
                    jid: {"status": j["status"], "started": j.get("started"), "pid": j.get("pid")}
                    for jid, j in _jobs.items()
                }
            self.send_json(summary)

        else:
            self.send_error(404)

    def do_POST(self):
        length  = int(self.headers.get("Content-Length", 0))
        body    = self.rfile.read(length)
        parsed  = urlparse(self.path)
        path    = parsed.path

        try:
            data = json.loads(body) if body else {}
        except Exception:
            data = {}

        if path == "/api/run":
            # Build command from { "args": ["--launch", "--model", "Qwen..."] }
            args    = data.get("args", [])
            python  = bundled_python()
            cmd     = [python, LUMINA_PY] + args
            job_id  = str(uuid.uuid4())[:8]
            threading.Thread(target=run_job, args=(job_id, cmd), daemon=True).start()
            self.send_json({"job_id": job_id})

        elif path == "/api/stop":
            job_id = data.get("job_id")
            with _jobs_lock:
                job = _jobs.get(job_id)
            if job and job.get("pid"):
                try:
                    import signal
                    os.kill(job["pid"], signal.SIGTERM)
                    with _jobs_lock:
                        _jobs[job_id]["status"] = "stopped"
                    self.send_json({"ok": True})
                except Exception as e:
                    self.send_json({"error": str(e)}, 500)
            else:
                self.send_json({"error": "Job not found or not running"}, 404)

        else:
            self.send_error(404)


def main():
    parser = argparse.ArgumentParser(description="Lumina Control Centre Server")
    parser.add_argument("--port", type=int, default=7777)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    os.makedirs(LOGS_DIR, exist_ok=True)

    server = HTTPServer((args.host, args.port), ControlHandler)
    url    = f"http://{args.host}:{args.port}"
    print(f"[+] Lumina Control Centre → {url}")

    # Open browser
    try:
        import webbrowser
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    except Exception:
        pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Shutting down Control Centre.")


if __name__ == "__main__":
    main()
