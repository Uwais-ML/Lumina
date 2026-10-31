"""
scripts/lumina_proxy.py
=======================
Ultra-lightweight, zero-downtime reverse proxy for Lumina & SmartSwitch.

Solves Criticism #3 (Uninstrumented Client Sockets):
External uninstrumented clients (such as standard curl or third-party web apps)
connecting to :8080 experience immediate ECONNREFUSED during the 0.04s same-port
rebind window when SmartSwitch performs a backend process switchover.

This async reverse proxy runs on the public ingress port (e.g. 8080), holds
client TCP connections open in-flight, retries the backend across the transient
rebind window, and transparently delivers the response once the replacement
model passes health checks.
"""

import sys
import os
import time
import socket
import select
import threading
import http.server
import urllib.request
import urllib.error

class LuminaBufferProxyHandler(http.server.BaseHTTPRequestHandler):
    backend_port = 8081  # Default internal backend port
    max_rebind_wait = 10.0  # Seconds to absorb port switchover gap

    def log_message(self, format, *args):
        # Quiet standard HTTP access logs
        pass

    def do_POST(self):
        self._proxy_request("POST")

    def do_GET(self):
        self._proxy_request("GET")

    def _proxy_request(self, method):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        target_url = f"http://127.0.0.1:{self.backend_port}{self.path}"
        headers = {k: v for k, v in self.headers.items() if k.lower() != "host"}

        deadline = time.time() + self.max_rebind_wait
        resp_data = None
        status_code = 502

        # In-flight absorption loop holding the downstream client socket open
        while time.time() < deadline:
            try:
                req = urllib.request.Request(target_url, data=body, headers=headers, method=method)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    status_code = resp.status
                    resp_data = resp.read()
                    resp_headers = resp.headers
                    break
            except (urllib.error.URLError, ConnectionRefusedError, socket.error):
                # Backend is in the 0.04s rebind window; sleep 20ms and retry
                time.sleep(0.02)

        if resp_data is not None:
            self.send_response(status_code)
            for k, v in resp_headers.items():
                if k.lower() not in ("transfer-encoding", "content-length"):
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(resp_data)))
            self.send_header("X-Lumina-Proxy", "absorbed-failover-rebind")
            self.end_headers()
            self.wfile.write(resp_data)
        else:
            self.send_error(504, "Lumina backend failed to recover within timeout")


def run_proxy(listen_port=8080, backend_port=8081):
    LuminaBufferProxyHandler.backend_port = backend_port
    server = http.server.ThreadingHTTPServer(("0.0.0.0", listen_port), LuminaBufferProxyHandler)
    print(f"[Lumina Proxy] Active on :{listen_port} -> forwarding to backend :{backend_port}")
    server.serve_forever()


if __name__ == "__main__":
    p_listen = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    p_backend = int(sys.argv[2]) if len(sys.argv) > 2 else 8081
    run_proxy(p_listen, p_backend)
