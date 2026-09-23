"""
conftest.py — shared pytest fixtures and helpers for Lumina test suite.
"""

import os
import sys
import socket
import subprocess
import time
import pytest

PROJECT_ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR   = os.path.join(PROJECT_ROOT, "scripts")
BUNDLED_SITE_PACKAGES = os.path.join(
    PROJECT_ROOT, "python-dependencies", "macos-intel", "lib", "python3.10", "site-packages"
)
RESOURCES_DIR = os.path.join(PROJECT_ROOT, "resources")
LLAMAFILE_BIN = os.path.join(RESOURCES_DIR, "llamafile", "llamafile-0.10.4-thin")
BANDWIDTH_TXT = os.path.join(RESOURCES_DIR, "bandwidth.txt")
MODELS_DIR    = os.path.join(PROJECT_ROOT, "models")
LOGS_DIR      = os.path.join(PROJECT_ROOT, "logs")
DATA_DIR      = os.path.join(PROJECT_ROOT, "data")

os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

if BUNDLED_SITE_PACKAGES not in sys.path:
    sys.path.insert(0, BUNDLED_SITE_PACKAGES)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_server(port: int, timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.4)
    return False


def launch_llamafile_server(model_name: str, port: int, log_path: str, ctx: int = 2048):
    """
    Launches llamafile via 'sh -c' (polyglot binary requirement).
    Returns (Popen, log_file_handle).
    """
    model_file = model_name if model_name.endswith(".gguf") else model_name + ".gguf"
    model_path = os.path.join(MODELS_DIR, model_file)

    if not os.path.exists(model_path):
        pytest.skip(f"Model not found: {model_path}")
    if not os.path.exists(LLAMAFILE_BIN):
        pytest.skip(f"llamafile binary missing: {LLAMAFILE_BIN}")

    os.chmod(LLAMAFILE_BIN, 0o755)
    shell_cmd = (
        f"'{LLAMAFILE_BIN}' --server "
        f"--host 127.0.0.1 --port {port} "
        f"-c {ctx} "
        f"-m '{model_path}'"
    )
    log_fh = open(log_path, "w")
    proc = subprocess.Popen(["sh", "-c", shell_cmd], stdout=log_fh, stderr=subprocess.STDOUT)
    return proc, log_fh, model_path


def kill_server(proc, log_fh, timeout: int = 6):
    """Gracefully terminates a llamafile server process."""
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
    if log_fh and not log_fh.closed:
        log_fh.close()


def delete_bandwidth_txt():
    if os.path.exists(BANDWIDTH_TXT):
        os.remove(BANDWIDTH_TXT)
        print("  🗑  Deleted bandwidth.txt")
    else:
        print("  ℹ  bandwidth.txt already absent")
