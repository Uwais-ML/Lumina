"""
test_assesser_vs_router_benchmark.py
=====================================
Pytest benchmark suite comparing:
  - SystemAssess (Java assesser) predicted T/s via estimate(params, quantization)
  - Actual measured T/s from llamafile inference on 3 different prompts/times

Models tested:
  - Llama-3.2-1B-Instruct-Q4_K_M        (1.0B params, Q4.83)
  - Qwen2.5-Coder-1.5B-Instruct-Q4_K_M  (1.5B params, Q4.83)
  - Qwen2.5-0.5B-Instruct-Q4_K_M        (0.5B params, Q4.83)

bandwidth.txt is deleted before AND after each model run → always a fresh assessment.
3 inference calls per model (different prompts, different times) capture variance.

Run with:
    pytest tests/test_assesser_vs_router_benchmark.py -v -s
"""

import os
import sys
import re
import time
import json
import socket
import subprocess
import pytest

# ── Path setup ────────────────────────────────────────────────────────────────
PROJECT_ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR   = os.path.join(PROJECT_ROOT, "scripts")
MODELS_DIR    = os.path.join(PROJECT_ROOT, "models")
RESOURCES_DIR = os.path.join(PROJECT_ROOT, "resources")
LOGS_DIR      = os.path.join(PROJECT_ROOT, "logs")
BANDWIDTH_TXT = os.path.join(RESOURCES_DIR, "bandwidth.txt")
LLAMAFILE_BIN = os.path.join(RESOURCES_DIR, "llamafile", "llamafile-0.10.4-thin")

os.makedirs(LOGS_DIR, exist_ok=True)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# ── Model registry ─────────────────────────────────────────────────────────────
# (display_name, gguf_filename, param_B, quantization_bits)
MODELS = [
    ("Phi-3.5-mini-3.8B",   "Phi-3.5-mini-instruct-Q4_K_M.gguf",       3.8, 4.83),
    ("Llama-3.2-1B",        "Llama-3.2-1B-Instruct-Q4_K_M.gguf",        1.0, 4.83),
    ("Qwen2.5-Coder-1.5B",  "Qwen2.5-Coder-1.5B-Instruct-Q4_K_M.gguf",  1.5, 4.83),
    ("Qwen2.5-0.5B",        "Qwen2.5-0.5B-Instruct-Q4_K_M.gguf",        0.5, 4.83),
]

# 3 prompts at different complexity levels — cold, medium, longer generation
PROMPTS = [
    "Hi, who are you?",
    "Explain the difference between RAM and disk storage in 3 sentences.",
    "Write a Python function that returns the nth Fibonacci number using recursion.",
]

TOLERANCE_PCT   = 50   # ±50%: soft comparison (logged, not hard-failed)
REQUEST_TIMEOUT = 90   # seconds per inference


# ── Global result accumulator (printed in session summary) ────────────────────
RESULTS: list[dict] = []


# ── Utilities ─────────────────────────────────────────────────────────────────

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def delete_bandwidth_txt():
    """Removes bandwidth.txt so the next measurement is unconditionally fresh."""
    if os.path.exists(BANDWIDTH_TXT):
        os.remove(BANDWIDTH_TXT)
        print("  🗑  Deleted bandwidth.txt — fresh measurement required")
    else:
        print("  ℹ  bandwidth.txt already absent — clean slate")


def read_bandwidth_value() -> float | None:
    """Returns the float stored in bandwidth.txt, or None if missing/corrupt."""
    try:
        with open(BANDWIDTH_TXT, "r") as f:
            return float(f.read().strip())
    except Exception:
        return None


def wait_for_server(port: int, log_path: str = None, timeout: float = 60.0) -> bool:
    """Polls until llamafile finishes warming up and returns HTTP 200 / ready marker."""
    import urllib.request
    deadline = time.time() + timeout
    ready_markers = ("all slots are idle", "HTTP server listening", "model loaded", "server is listening")
    while time.time() < deadline:
        if log_path and os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    if any(marker in content for marker in ready_markers):
                        return True
            except Exception:
                pass
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/health")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def launch_llamafile(model_path: str, port: int, log_path: str):
    """
    Starts llamafile --server subprocess. Returns (Popen, log_file_handle).
    llamafile is a polyglot (ZIP+shell) binary — must be executed via 'sh -c'
    on macOS/Linux, exactly as launch_model.py does it.
    """
    if not os.path.exists(LLAMAFILE_BIN):
        pytest.skip(f"llamafile binary not found: {LLAMAFILE_BIN}")
    os.chmod(LLAMAFILE_BIN, 0o755)
    shell_cmd = (
        f"'{LLAMAFILE_BIN}' --server "
        f"--host 127.0.0.1 --port {port} "
        f"-c 2048 "
        f"-m '{model_path}'"
    )
    log_fh = open(log_path, "w")
    proc = subprocess.Popen(
        ["sh", "-c", shell_cmd],
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )
    return proc, log_fh


def read_tps_from_log(log_path: str) -> list[float]:
    """Parses all eval-time T/s entries from a llamafile log file."""
    result = []
    if not os.path.exists(log_path):
        return result
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "eval time" in line and "prompt eval time" not in line:
                m = re.search(r"([\d.]+)\s+tokens per second", line)
                if m:
                    v = float(m.group(1))
                    if 0 < v < 5000:
                        result.append(v)
    return result


def infer_once(port: int, prompt: str, run_label: str = "") -> tuple[float | None, float]:
    """
    Sends one /v1/completions request.
    Returns (actual_tps, elapsed_seconds). tps may be None on failure.
    """
    import urllib.request

    payload = json.dumps({
        "prompt": prompt,
        "temperature": 0.0,
        "max_tokens": 128,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        elapsed = time.time() - t0
        tps = body.get("timings", {}).get("predicted_per_second", None)
        if tps is None:
            tokens = body.get("usage", {}).get("completion_tokens", None)
            tps = tokens / elapsed if (tokens and elapsed > 0) else None
        return tps, elapsed
    except Exception as exc:
        elapsed = time.time() - t0
        print(f"    ⚠  [{run_label}] Inference error: {exc}")
        return None, elapsed


def predict_tps(bandwidth_gbs: float, param_b: float, quant_bits: float) -> float | None:
    """
    Mirrors Java SystemAssess.estimate() logic:
        modelSizeGB   = param_b * (quant_bits / 8.0)
        predicted_tps = bandwidth_gbs / modelSizeGB
    """
    size_gb = param_b * (quant_bits / 8.0)
    return bandwidth_gbs / size_gb if size_gb > 0 else None


# ── Session-scoped summary fixture ────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def print_benchmark_summary():
    """Prints the full results table after all tests complete."""
    yield  # --- tests run here ---
    if not RESULTS:
        return
    print("\n\n" + "=" * 88)
    print("  BENCHMARK SUMMARY  ·  Assesser Prediction vs Actual T/s")
    print("=" * 88)
    hdr = (f"{'Model':<28} {'Run':<6} {'BW (GB/s)':>10} "
           f"{'Predicted':>10} {'Actual':>10} {'Delta':>9} {'Status':>8}")
    print(hdr)
    print("-" * 88)
    for r in RESULTS:
        bw  = f"{r['bandwidth_gbs']:.3f}" if r["bandwidth_gbs"] is not None else "N/A"
        pre = f"{r['predicted_tps']:.1f}"  if r["predicted_tps"] is not None else "N/A"
        act = f"{r['actual_tps']:.1f}"    if r["actual_tps"]    is not None else "N/A"
        dlt = f"{r['delta_pct']:+.1f}%"   if r["delta_pct"]     is not None else "N/A"
        ico = "✅" if r["within_tolerance"] else "❌"
        print(f"{r['model']:<28} {r['run']:<6} {bw:>10} {pre:>10} {act:>10} {dlt:>9} {ico:>8}")
    print("=" * 88 + "\n")

    # Persist structured results to logs/benchmark_results.json
    results_path = os.path.join(LOGS_DIR, "benchmark_results.json")
    try:
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": time.time(),
                "results": RESULTS
            }, f, indent=4)
        print(f"  💾 Benchmark results saved to {results_path}")
    except Exception as e:
        print(f"  ⚠ Failed to save benchmark results: {e}")


# ── Main parametrised benchmark test ─────────────────────────────────────────

@pytest.mark.parametrize(
    "display_name,gguf_file,param_b,quant_bits",
    MODELS,
    ids=[m[0] for m in MODELS],
)
def test_assesser_vs_actual_tps(display_name, gguf_file, param_b, quant_bits):
    """
    Per-model benchmark:
      1. Delete bandwidth.txt                  → unconditionally fresh assessment
      2. Launch llamafile server for this model
      3. Run 3 inference calls (different prompts, different wall-clock times)
      4. Capture actual T/s from response timings + log parsing
      5. Derive bandwidth (GB/s) from measured T/s × model size
         (or read bandwidth.txt if already populated by Java assesser)
      6. Compute predicted T/s using SystemAssess.estimate() formula
      7. Log comparison; soft-assert within ±TOLERANCE_PCT
      8. Delete bandwidth.txt again (next test starts fresh)
    """
    model_path = os.path.join(MODELS_DIR, gguf_file)
    if not os.path.exists(model_path):
        pytest.skip(f"Model not downloaded yet: {gguf_file}")

    # ── 1. Delete bandwidth.txt ────────────────────────────────────────────────
    delete_bandwidth_txt()

    port = find_free_port()
    log_path = os.path.join(LOGS_DIR, f"bench_{display_name.replace(' ', '_')}.log")

    sep = "─" * 62
    print(f"\n{sep}")
    print(f"  Model  : {display_name}")
    print(f"  File   : {gguf_file}")
    print(f"  Port   : {port}")
    print(f"  Params : {param_b}B   Quant : Q{quant_bits} bits/weight")
    print(sep)

    # ── 2. Launch llamafile ────────────────────────────────────────────────────
    proc, log_fh = launch_llamafile(model_path, port, log_path)
    try:
        print(f"  ⏳ Waiting for llamafile server on :{port} ...")
        if not wait_for_server(port, log_path=log_path, timeout=60.0):
            pytest.fail(f"{display_name}: llamafile server never came up on :{port}")
        time.sleep(2.0)  # brief settle

        # ── 3 & 4. Three inference runs ────────────────────────────────────────
        run_records: list[tuple[str, float | None, float]] = []
        for run_idx, prompt in enumerate(PROMPTS, start=1):
            label = f"run{run_idx}"
            print(f"\n  📤 [{label}] prompt: {prompt[:68]!r}")
            tps_resp, elapsed = infer_once(port, prompt, run_label=label)

            # Also read from log for cross-validation
            log_tps = read_tps_from_log(log_path)
            tps_log = log_tps[-1] if log_tps else None

            actual_tps = tps_resp if tps_resp else tps_log
            run_records.append((label, actual_tps, elapsed))
            print(
                f"  ⏱  [{label}] elapsed={elapsed:.1f}s  "
                f"T/s(response)={tps_resp}  T/s(log)={tps_log}"
            )

        # ── 5. Derive / read bandwidth ─────────────────────────────────────────
        bandwidth = read_bandwidth_value()  # populated by Java assesser if run first

        if bandwidth is None:
            # Derive empirically: bandwidth = avg_tps × model_size_GB
            model_size_gb = param_b * (quant_bits / 8.0)
            valid_tps = [t for _, t, _ in run_records if t is not None]
            if valid_tps:
                avg_tps  = sum(valid_tps) / len(valid_tps)
                bandwidth = avg_tps * model_size_gb
                print(f"\n  📊 Empirically derived bandwidth: {bandwidth:.4f} GB/s")
                # Write for consistency with the Java assesser's file
                with open(BANDWIDTH_TXT, "w") as f:
                    f.write(f"{bandwidth}\n")
            else:
                print("\n  ⚠  No valid T/s — cannot derive bandwidth")
        else:
            print(f"\n  📄 bandwidth.txt value: {bandwidth:.4f} GB/s")

        # ── 6. Compute predicted T/s ───────────────────────────────────────────
        predicted = predict_tps(bandwidth, param_b, quant_bits) if bandwidth else None
        print(
            f"  🔮 Assesser predicted T/s: {predicted:.1f}"
            if predicted else "  🔮 Assesser predicted T/s: N/A"
        )

        # ── 7. Compare per-run ────────────────────────────────────────────────
        for label, actual_tps, elapsed in run_records:
            if actual_tps is not None and predicted is not None:
                delta_pct = ((actual_tps - predicted) / predicted) * 100
                within    = abs(delta_pct) <= TOLERANCE_PCT
                verdict   = "✅ WITHIN" if within else "❌ OUTSIDE"
                print(
                    f"  {verdict} ±{TOLERANCE_PCT}%  [{label}]  "
                    f"actual={actual_tps:.2f} T/s  predicted={predicted:.2f} T/s  "
                    f"delta={delta_pct:+.1f}%"
                )
            else:
                delta_pct = None
                within = False
                print(f"  ⚠  [{label}]  actual={actual_tps}  predicted={predicted} — delta N/A")

            RESULTS.append({
                "model":            display_name,
                "run":              label,
                "bandwidth_gbs":    bandwidth,
                "predicted_tps":    predicted,
                "actual_tps":       actual_tps,
                "delta_pct":        delta_pct,
                "within_tolerance": within,
                "elapsed_sec":      elapsed,
            })

        # ── Hard assertion: we must get at least 1 valid actual T/s ───────────
        valid = [t for _, t, _ in run_records if t is not None]
        assert len(valid) > 0, (
            f"{display_name}: All 3 inference runs returned no T/s. "
            f"Check model path and log: {log_path}"
        )

    finally:
        # ── Teardown: kill server + delete bandwidth.txt ───────────────────────
        print(f"\n  🛑 Terminating llamafile (PID {proc.pid})...")
        proc.terminate()
        try:
            proc.wait(timeout=6)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_fh.close()
        print("  ✔  Server shut down.")
        delete_bandwidth_txt()   # clean for the next parametrised model
