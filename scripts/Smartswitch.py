import os
import sys
import time
import json
import logging
import argparse
import re
import psutil

Killed_model = None

# Add scripts directory to sys.path so we can import launch_model cleanly
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import launch_model

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
STATUS_FILE = os.path.join(DATA_DIR, "status.txt")
QUERY_BUFFER_FILE = os.path.join(DATA_DIR, "query_buffer.json")


# ---------------------------------------------------------------------------
# Query Buffer Subsystem
# ---------------------------------------------------------------------------

def store_query_buffer(prompt_or_payload, endpoint="/v1/chat/completions", port=None, buffer_file=QUERY_BUFFER_FILE):
    """
    Stores an active query into the query buffer before token generation begins.
    The buffer holds the query until the response is fully generated.
    """
    try:
        os.makedirs(os.path.dirname(buffer_file), exist_ok=True)
        buffer_data = {
            "status": "PROCESSING",
            "timestamp": time.time(),
            "port": port,
            "endpoint": endpoint,
            "payload": prompt_or_payload,
            "retry_count": 0,
        }
        with open(buffer_file, "w", encoding="utf-8") as f:
            json.dump(buffer_data, f, indent=4)
        logging.debug(f"📥 Query buffered (status: PROCESSING, port: {port}, endpoint: {endpoint})")
        return buffer_data
    except Exception as e:
        logging.error(f"Error storing query in buffer: {e}")
        return None


def get_active_query(buffer_file=QUERY_BUFFER_FILE):
    """
    Retrieves the currently pending query from buffer if one is processing or failed over.
    Returns None if no query is active.
    """
    if not os.path.exists(buffer_file) or os.path.getsize(buffer_file) == 0:
        return None
    try:
        with open(buffer_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if data.get("status") in ("PROCESSING", "FAILED_OVER", "RETRYING"):
                return data
    except Exception as e:
        logging.error(f"Error reading query buffer: {e}")
    return None


def release_query_buffer(buffer_file=QUERY_BUFFER_FILE):
    """
    Releases / clears the query buffer once response generation is complete,
    making it ready to store the next query.
    """
    try:
        if os.path.exists(buffer_file):
            buffer_data = {
                "status": "IDLE",
                "timestamp": time.time(),
                "payload": None,
            }
            with open(buffer_file, "w", encoding="utf-8") as f:
                json.dump(buffer_data, f, indent=4)
            logging.debug("📤 Query buffer released and ready for next query.")
            return True
    except Exception as e:
        logging.error(f"Error releasing query buffer: {e}")
    return False


def replay_buffered_query(port=None, timeout=60, buffer_file=QUERY_BUFFER_FILE):
    """
    Replays the currently buffered query to the fallback model on the designated port.
    Returns the response JSON or text if successful, or None.
    """
    import requests
    active_query = get_active_query(buffer_file)
    if not active_query:
        logging.info("No active query in buffer to replay.")
        return None

    target_port = port or active_query.get("port") or 8080
    endpoint = active_query.get("endpoint", "/v1/chat/completions")
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    url = f"http://127.0.0.1:{target_port}{endpoint}"
    payload = active_query.get("payload")

    logging.info(f"🔄 Replaying saved query from buffer to fallback model at {url}...")
    try:
        if isinstance(payload, dict):
            res = requests.post(url, json=payload, timeout=timeout)
        elif isinstance(payload, str):
            res = requests.post(url, data=payload, headers={"Content-Type": "application/json"}, timeout=timeout)
        else:
            res = requests.post(url, json=payload, timeout=timeout)

        if res.status_code == 200:
            logging.info("✔ Successfully received response from fallback model for buffered query.")
            release_query_buffer(buffer_file)
            try:
                return res.json()
            except Exception:
                return res.text
        else:
            logging.warning(f"Fallback replay returned status {res.status_code}: {res.text}")
    except Exception as e:
        logging.error(f"Error during buffered query replay: {e}")

    return None


def safe_query(
    url_or_port,
    payload=None,
    endpoint="/v1/chat/completions",
    timeout=60,
    max_retries=3,
    retry_delay=2.0,
    buffer_file=QUERY_BUFFER_FILE,
    **kwargs,
):
    """
    Resilient query dispatcher:
    1. Saves the query in the buffer before sending.
    2. Sends the query to the active model.
    3. If mid-generation failover occurs (connection drop/reset when SmartSwitch terminates the model),
       waits for the fallback model to come online on the same port and replays the buffered query seamlessly.
    4. Upon successful generation, releases the query buffer.
    """
    import requests

    if isinstance(url_or_port, int) or (isinstance(url_or_port, str) and url_or_port.isdigit()):
        port = int(url_or_port)
        if not endpoint.startswith("/"):
            endpoint = "/" + endpoint
        url = f"http://127.0.0.1:{port}{endpoint}"
    else:
        url = str(url_or_port)
        port = None
        match = re.search(r":(\d+)", url)
        if match:
            port = int(match.group(1))

    # 1. Save query to buffer
    store_query_buffer(payload, endpoint=endpoint, port=port, buffer_file=buffer_file)

    for attempt in range(max_retries + 1):
        try:
            if isinstance(payload, dict):
                resp = requests.post(url, json=payload, timeout=timeout, **kwargs)
            else:
                resp = requests.post(url, data=payload, timeout=timeout, **kwargs)

            if resp.status_code == 200:
                # Release buffer upon successful completion
                release_query_buffer(buffer_file)
                return resp
            else:
                logging.warning(f"Query attempt {attempt + 1} returned status {resp.status_code}. Waiting for model...")
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.RequestException) as e:
            logging.warning(
                f"⚠️ Connection interrupted during query (Attempt {attempt + 1}/{max_retries + 1}): {e}. "
                f"SmartSwitch may be hot-swapping the model on port {port}. Retrying buffered query..."
            )

        # Wait for fallback model to become ready on the same port
        time.sleep(retry_delay)

    # If all retries failed, release buffer
    release_query_buffer(buffer_file)
    return None


# ---------------------------------------------------------------------------
# GPU / VRAM helpers
# ---------------------------------------------------------------------------

def is_cuda_available():
    """Returns True if a CUDA-capable GPU is present and accessible."""
    try:
        import torch
        return torch.cuda.is_available()
    except Exception:
        pass
    # Fallback: check if nvidia-smi is reachable
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except Exception:
        return False


def get_vram_usage_bytes(gpu_index=0):
    """
    Returns current GPU VRAM used (bytes) using the best available library.

    Priority order:
      1. pynvml  — system-wide VRAM used (best for non-PyTorch processes like llamafile)
      2. nvidia-smi subprocess — fallback when pynvml is not installed
      3. torch.cuda.memory_reserved — PyTorch-allocated only (least accurate for llamafile)
      4. None — no GPU detected / no library available

    Parameters
    ----------
    gpu_index : int
        GPU device index (for multi-GPU machines). Default 0.
    """
    # 1. pynvml — most reliable, covers all GPU processes including llamafile
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_index)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        pynvml.nvmlShutdown()
        return int(mem.used)
    except Exception:
        pass

    # 2. nvidia-smi subprocess
    try:
        import subprocess
        result = subprocess.run(
            [
                "nvidia-smi",
                f"--id={gpu_index}",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            used_mib = float(result.stdout.strip().split("\n")[0].strip())
            return int(used_mib * 1024 * 1024)
    except Exception:
        pass

    # 3. torch.cuda — PyTorch-allocated only, fallback
    try:
        import torch
        if torch.cuda.is_available():
            return int(torch.cuda.memory_reserved(gpu_index))
    except Exception:
        pass

    return None


def killprocess(pid, timeout=3):
    """Gracefully terminates a process by PID, falling back to SIGKILL if needed."""
    try:
        if not psutil.pid_exists(pid):
            logging.info(f"Process with PID {pid} is already stopped.")
            return True
        process = psutil.Process(pid)
        process.terminate()
        try:
            process.wait(timeout=timeout)
        except (psutil.TimeoutExpired, psutil.NoSuchProcess):
            if process.is_running():
                process.kill()
                process.wait(timeout=2)
        logging.warning(f"Process with PID {pid} successfully terminated.")
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        logging.warning(f"Could not kill process {pid}: {e}")
        return False



def savecontext(log_path):
    """Extracts server listening port/url from a llamafile log file."""
    if not os.path.exists(log_path):
        return None
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "server is listening" in line or "HTTP server listening" in line:
                    parts = line.split()
                    for p in parts:
                        if ":" in p and any(char.isdigit() for char in p):
                            return p.strip()
    except Exception as e:
        logging.error(f"Error reading context from {log_path}: {e}")
    return None


def wait_for_model_ready(pid, port=None, log_file=None, timeout=30.0, settle_time=3.0):
    """
    Waits for a model process to finish loading weights and initialize server.
    Monitors process existence, logs for readiness markers, and stabilizes RSS memory.

    Returns the stabilized peak RSS in bytes, or None if process exited.
    """
    if not psutil.pid_exists(pid):
        return None

    try:
        proc = psutil.Process(pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None

    ready_markers = (
        "server is listening",
        "HTTP server listening",
        "model loaded",
        "all slots are idle",
    )

    start_time = time.time()
    is_ready = False

    # 1. Wait for server readiness marker up to timeout
    while time.time() - start_time < timeout:
        if not psutil.pid_exists(pid) or not proc.is_running():
            return None

        # Check log file if available
        if log_file and os.path.exists(log_file):
            try:
                with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    if any(marker in content for marker in ready_markers):
                        is_ready = True
                        break
            except Exception:
                pass

        time.sleep(0.5)

    if is_ready:
        logging.debug(f"Model process (PID: {pid}) signaled ready. Allowing {settle_time}s memory stabilization...")
    else:
        logging.debug(f"Readiness signal not found for PID {pid} after {timeout}s; proceeding with {settle_time}s memory stabilization...")

    # 2. Settle period to let RSS memory / mmap allocations stabilize
    settle_start = time.time()
    peak_rss = 0
    while time.time() - settle_start < settle_time:
        if not psutil.pid_exists(pid) or not proc.is_running():
            return None
        try:
            current_rss = proc.memory_info().rss
            if current_rss > peak_rss:
                peak_rss = current_rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None
        time.sleep(0.5)

    return peak_rss


def raminitilization(
    model_name,
    pid,
    port=None,
    log_file=None,
    vram_delta_mb=300,
    no_vram=False,
    gpu_index=0,
    settle_time=3.0,
    init_timeout=30.0,
):
    """
    Initializes and records model PID, port, baseline RAM or VRAM, log file
    path, T/s, and tracking MODE ("ram" | "vram") in status.txt after allowing
    the model to fully initialize and settle into memory.

    Parameters
    ----------
    model_name    : str   — model filename or clean name
    pid           : int   — PID of the launched process
    port          : int   — allocated server port
    log_file      : str   — path to llamafile log
    vram_delta_mb : float — RAM growth threshold (MB) below which VRAM mode is used
    no_vram       : bool  — if True, always track RAM regardless of CUDA
    gpu_index     : int   — GPU device index for VRAM query
    settle_time   : float — Seconds to allow memory stabilization after ready signal
    init_timeout  : float — Max seconds to wait for model ready signal
    """
    try:
        os.makedirs(DATA_DIR, exist_ok=True)

        if not psutil.pid_exists(pid):
            logging.error(f"Cannot initialize: Process PID {pid} does not exist.")
            return

        key = model_name[:-5] if model_name.endswith(".gguf") else model_name
        if not log_file:
            log_file = get_model_log_file(key)

        logging.debug(
            f"⏳ Initializing baseline memory for '{key}' (PID: {pid}). "
            f"Waiting up to {init_timeout}s for load + {settle_time}s settle time..."
        )

        post_rss_bytes = wait_for_model_ready(
            pid,
            port=port,
            log_file=log_file,
            timeout=init_timeout,
            settle_time=settle_time,
        )

        if post_rss_bytes is None or not psutil.pid_exists(pid):
            logging.error(f"Process PID {pid} died or could not be read during initialization wait.")
            return

        proc_tracker = psutil.Process(pid)
        current_rss_bytes = proc_tracker.memory_info().rss
        if current_rss_bytes > post_rss_bytes:
            post_rss_bytes = current_rss_bytes

        ram_mb = post_rss_bytes / (1024 * 1024)

        # Determine tracking mode
        cuda_present = is_cuda_available()
        vram_bytes = get_vram_usage_bytes(gpu_index) if (cuda_present and not no_vram) else None
        use_vram = (
            cuda_present
            and not no_vram
            and vram_bytes is not None
            and vram_bytes > 0
            and ram_mb < vram_delta_mb
        )

        status_data = {}
        if os.path.exists(STATUS_FILE) and os.path.getsize(STATUS_FILE) > 0:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                try:
                    status_data = json.load(f)
                except json.JSONDecodeError:
                    status_data = {}

        # Check if any initial non-zero T/s is already present in logs
        initial_tps_list = [t for t in parse_eval_tokens_per_second(log_file) if t > 0.0]
        initial_tps = round(initial_tps_list[-1], 2) if initial_tps_list else 0.0
        baseline_tps = round(initial_tps_list[0], 2) if initial_tps_list else None

        if use_vram:
            vram_gb = vram_bytes / (1024 ** 3)
            status_data[key] = {
                "PID": int(pid),
                "PORT": int(port) if port is not None else None,
                "MODE": "vram",
                "VRAM": f"{vram_gb:.2f} GB",
                "RAM": f"{post_rss_bytes / (1024 ** 3):.2f} GB",
                "T/s": initial_tps,
                "BASELINE_TPS": baseline_tps,
                "LOG_FILE": log_file,
                "INITIALIZED_AT": time.time(),
            }
            logging.info(
                f"Model '{key}' initialized in VRAM mode "
                f"(PID: {pid}, Port: {port}, VRAM: {vram_gb:.2f} GB, "
                f"RAM: {ram_mb:.1f} MB, Log: {log_file})"
            )
        else:
            ram_gb = post_rss_bytes / (1024 ** 3)
            status_data[key] = {
                "PID": int(pid),
                "PORT": int(port) if port is not None else None,
                "MODE": "ram",
                "RAM": f"{ram_gb:.2f} GB",
                "T/s": initial_tps,
                "BASELINE_TPS": baseline_tps,
                "LOG_FILE": log_file,
                "INITIALIZED_AT": time.time(),
            }
            logging.info(
                f"Model '{key}' initialized in RAM mode "
                f"(PID: {pid}, Port: {port}, RAM: {ram_gb:.2f} GB, Log: {log_file})"
            )

        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(status_data, f, indent=4)

    except Exception as e:
        logging.error(f"Error saving model details for {model_name}: {e}")

# Alias for backward compatibility
ram_initialization = raminitilization



def get_model_log_file(model_name, info=None):
    """Returns the expected log file path for a model."""
    if isinstance(info, dict) and info.get("LOG_FILE") and os.path.exists(info["LOG_FILE"]):
        return info["LOG_FILE"]

    clean_name = model_name[:-5] if model_name.endswith(".gguf") else model_name
    candidates = [
        os.path.join(LOGS_DIR, f"llamafile_{clean_name}.log"),
        os.path.join(LOGS_DIR, f"{clean_name}.log"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0]


def parse_eval_tokens_per_second(log_file_path):
    """Parses evaluation tokens/second history from llamafile server logs."""
    tps_history = []
    if not os.path.exists(log_file_path):
        return tps_history

    try:
        with open(log_file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                # Look for eval time lines (exclude prompt eval time which is prompt ingestion speed)
                # e.g., "eval time = 204.69 ms / 15 tokens ( 13.65 ms per token, 73.28 tokens per second)"
                if "eval time" in line and "prompt eval time" not in line:
                    match = re.search(r'([\d.]+)\s+tokens per second', line)
                    if match:
                        try:
                            tps = float(match.group(1))
                            if tps > 0:
                                tps_history.append(tps)
                        except ValueError:
                            pass
                    elif "(" in line and ")" in line:
                        inside = line[line.find("(") + 1: line.find(")")]
                        segments = inside.split(",")
                        if len(segments) > 1:
                            try:
                                tps = float(segments[1].split()[0])
                                if tps > 0:
                                    tps_history.append(tps)
                            except (ValueError, IndexError):
                                pass
    except Exception as e:
        logging.error(f"Error parsing log file {log_file_path}: {e}")

    return tps_history



def runforever(
    base_model="Qwen2.5-0.5B-Instruct-Q4_K_M",
    ram_allowance=0.25,
    check_interval=2.0,
    tps_threshold=0.75,
    min_tps_samples=2,
    kill_timeout=3,
    socket_wait=1.5,
    vram_delta_mb=300,
    no_vram=False,
    gpu_index=0,
    log_level="INFO",
    settle_time=3.0,
    init_timeout=30.0,
    grace_period=10.0,
    buffer_file=QUERY_BUFFER_FILE,
    auto_replay=True,
):
    """
    Monitors active LLM processes continuously during token generation. If memory
    (RAM or VRAM) inflates past the threshold or inference speed drops below
    tps_threshold of baseline during generation, the degraded model is replaced
    by base_model on the exact same port and the buffered query is automatically replayed.

    Parameters
    ----------
    base_model       : str   — Fallback model name (without .gguf)
    ram_allowance    : float — Fractional tolerance above baseline (0.25 = 25%)
    check_interval   : float — Monitoring loop sleep time in seconds
    tps_threshold    : float — Fraction of baseline T/s below which switch triggers
    min_tps_samples  : int   — Minimum T/s samples before degradation check activates
    kill_timeout     : float — Seconds before SIGKILL after SIGTERM
    socket_wait      : float — Seconds to wait after kill before relaunching on same port
    vram_delta_mb    : float — RAM growth (MB) below which VRAM mode is inferred
    no_vram          : bool  — Disable VRAM tracking, always use RAM
    gpu_index        : int   — GPU device index for VRAM queries
    log_level        : str   — Python logging level name
    settle_time      : float — Settle duration for fallback initialization
    init_timeout     : float — Timeout for fallback initialization
    grace_period     : float — Grace period (s) after initialization to avoid false alarms
    buffer_file      : str   — Path to query buffer file
    auto_replay      : bool  — Automatically replay buffered query to fallback model
    """
    global Killed_model

    # Apply log level
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logging.getLogger().setLevel(numeric_level)

    logging.info(
        f"🚀 Smart Switch started. "
        f"Fallback: '{base_model}' | "
        f"Allowance: {ram_allowance * 100:.0f}% | "
        f"Interval: {check_interval}s | "
        f"TPS threshold: {tps_threshold * 100:.0f}% | "
        f"Grace period: {grace_period}s | "
        f"Query buffer: '{buffer_file}' (auto_replay={auto_replay}) | "
        f"VRAM mode: {'disabled' if no_vram else f'auto (delta < {vram_delta_mb} MB)'}"
    )

    base_model_clean = base_model[:-5] if base_model.endswith(".gguf") else base_model

    while True:
        try:
            if not os.path.exists(STATUS_FILE) or os.path.getsize(STATUS_FILE) == 0:
                logging.info("Status tracker file is empty or missing. Waiting for models to launch...")
                time.sleep(5)
                continue

            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                try:
                    status_data = json.load(f)
                except json.JSONDecodeError:
                    status_data = {}

            if not status_data:
                time.sleep(check_interval)
                continue

            updated_status = False

            # Safe iteration over a snapshot of items
            for key, info in list(status_data.items()):
                pid = info.get("PID")
                allocated_port = info.get("PORT")
                mode = info.get("MODE", "ram")  # "ram" or "vram"

                if not pid or not psutil.pid_exists(pid):
                    logging.warning(f"Process for model '{key}' (PID: {pid}) is no longer active.")
                    del status_data[key]
                    updated_status = True
                    continue

                process = psutil.Process(pid)
                if not process.is_running():
                    del status_data[key]
                    updated_status = True
                    continue

                init_time = info.get("INITIALIZED_AT")
                in_grace = (time.time() - init_time < grace_period) if init_time else False

                # ── 1. Memory check — RAM or VRAM depending on mode ──────────
                mem_exceeded = False

                if mode == "vram":
                    current_vram_bytes = get_vram_usage_bytes(gpu_index)
                    if current_vram_bytes is not None:
                        current_vram_gb = current_vram_bytes / (1024 ** 3)
                        prev_vram_str = info.get("VRAM", "0 GB").replace(" GB", "")
                        try:
                            prev_vram_gb = float(prev_vram_str)
                        except ValueError:
                            prev_vram_gb = current_vram_gb

                        threshold_factor = (1.0 + ram_allowance) if ram_allowance <= 1.0 else 1.25
                        threshold_gb = threshold_factor * prev_vram_gb

                        mem_exceeded = current_vram_gb > threshold_gb
                        if mem_exceeded:
                            if in_grace:
                                logging.info(
                                    f"Model '{key}' VRAM is {current_vram_gb:.2f} GB during initial grace period. "
                                    f"Updating baseline to {current_vram_gb:.2f} GB."
                                )
                                info["VRAM"] = f"{current_vram_gb:.2f} GB"
                                updated_status = True
                                mem_exceeded = False
                            else:
                                logging.warning(
                                    f"⚠️ High VRAM for '{key}': "
                                    f"current {current_vram_gb:.2f} GB exceeds "
                                    f"baseline {prev_vram_gb:.2f} GB "
                                    f"(threshold {threshold_gb:.2f} GB)"
                                )
                        else:
                            logging.debug(
                                f"VRAM '{key}': {current_vram_gb:.2f} GB / "
                                f"threshold {threshold_gb:.2f} GB — OK"
                            )
                    else:
                        # VRAM query failed — fall back to RAM check gracefully
                        logging.debug(f"VRAM query failed for '{key}', falling back to RAM check.")
                        mode = "ram"

                if mode == "ram":
                    mem_info = process.memory_info()
                    ram_mb = mem_info.rss / (1024 * 1024)
                    prev_ram_str = info.get("RAM", "0 GB").replace(" GB", "")
                    try:
                        prev_ram_mb = float(prev_ram_str) * 1024
                    except ValueError:
                        prev_ram_mb = ram_mb

                    # Auto-calibrate baseline if it was recorded prematurely (< 50MB) before model weights loaded
                    if prev_ram_mb < 50 and ram_mb >= 50:
                        logging.info(
                            f"Model '{key}' baseline was recorded before weights loaded "
                            f"({prev_ram_mb:.1f} MB). Auto-calibrating baseline to {ram_mb:.1f} MB."
                        )
                        info["RAM"] = f"{ram_mb / 1024:.2f} GB"
                        prev_ram_mb = ram_mb
                        updated_status = True

                    threshold_factor = (1.0 + ram_allowance) if ram_allowance <= 1.0 else 1.25
                    threshold_mb = threshold_factor * prev_ram_mb

                    mem_exceeded = ram_mb > threshold_mb
                    if mem_exceeded:
                        if in_grace:
                            logging.info(
                                f"Model '{key}' RAM is {ram_mb:.1f} MB during initial grace period. "
                                f"Updating baseline to {ram_mb / 1024:.2f} GB."
                            )
                            info["RAM"] = f"{ram_mb / 1024:.2f} GB"
                            updated_status = True
                            mem_exceeded = False
                        else:
                            logging.warning(
                                f"⚠️ High RAM for '{key}': "
                                f"current {ram_mb:.1f} MB exceeds "
                                f"baseline {prev_ram_mb:.1f} MB "
                                f"(threshold {threshold_mb:.1f} MB)"
                            )

                # ── 2. T/s performance degradation check ─────────────────────
                log_file = get_model_log_file(key, info)
                raw_tps_history = parse_eval_tokens_per_second(log_file)
                # Keep strictly positive (non-zero) T/s measurements
                tps_history = [t for t in raw_tps_history if t > 0.0]
                perf_degraded = False

                if tps_history:
                    # Resolve baseline T/s: use stored baseline if valid, otherwise establish first non-zero T/s
                    saved_baseline = info.get("BASELINE_TPS")
                    if saved_baseline is not None and isinstance(saved_baseline, (int, float)) and saved_baseline > 0:
                        baseline_tps = float(saved_baseline)
                    else:
                        baseline_tps = tps_history[0]
                        info["BASELINE_TPS"] = round(baseline_tps, 2)
                        logging.info(
                            f"📊 First prompt executed! Established baseline speed for '{key}': {baseline_tps:.2f} T/s"
                        )
                        updated_status = True

                    current_tps = tps_history[-1]
                    current_tps_rounded = round(current_tps, 2)
                    if info.get("T/s") != current_tps_rounded:
                        info["T/s"] = current_tps_rounded
                        updated_status = True

                    # Check for degradation once we have at least min_tps_samples non-zero runs
                    if len(tps_history) >= min_tps_samples and baseline_tps > 0:
                        if current_tps < (tps_threshold * baseline_tps):
                            logging.warning(
                                f"⚠️ Speed degradation for '{key}' detected mid-generation: "
                                f"baseline={baseline_tps:.2f} T/s → "
                                f"current={current_tps:.2f} T/s "
                                f"(< {tps_threshold * 100:.0f}%)"
                            )
                            perf_degraded = True


                # ── 3. Trigger Smart Switch ───────────────────────────────────
                if (perf_degraded or mem_exceeded) and key != base_model_clean:
                    reason = []
                    if mem_exceeded:
                        reason.append(f"{'VRAM' if info.get('MODE') == 'vram' else 'RAM'} exceeded")
                    if perf_degraded:
                        reason.append("T/s degraded mid-generation")

                    logging.critical(
                        f"🚨 Triggering Smart Switch! Replacing '{key}' with "
                        f"'{base_model_clean}' on port {allocated_port}. "
                        f"Reason: {', '.join(reason)}"
                    )

                    # Check query buffer before killing degraded model
                    active_query = get_active_query(buffer_file)
                    if active_query:
                        logging.info(
                            f"📥 Active query detected in buffer during generation interruption. "
                            f"Preserving query for replay to fallback '{base_model_clean}' on port {allocated_port}."
                        )

                    killprocess(pid, timeout=kill_timeout)
                    Killed_model = key
                    time.sleep(socket_wait)  # allow OS to fully release the socket

                    # Auto-embed accumulated context into Chroma for seamless continuity
                    try:
                        import classifier
                        logging.info("🧠 Smart Switch: Embedding session context into Chroma DB...")
                        classifier.embed_context_file()
                    except Exception as ce:
                        logging.warning(f"Could not auto-embed context during switch: {ce}")

                    # Launch fallback model on the exact same port
                    launch_result = launch_model.launchmodel(
                        base_model,
                        port=allocated_port,
                        startup_timeout=init_timeout,
                    )

                    del status_data[key]

                    if launch_result and "pid" in launch_result:
                        new_pid = launch_result["pid"]
                        new_port = launch_result["port"]
                        new_log = launch_result.get("log_file")
                        raminitilization(
                            base_model_clean,
                            new_pid,
                            port=new_port,
                            log_file=new_log,
                            vram_delta_mb=vram_delta_mb,
                            no_vram=no_vram,
                            gpu_index=gpu_index,
                            settle_time=settle_time,
                            init_timeout=init_timeout,
                        )

                        # Re-read status_data after raminitilization writes it
                        if os.path.exists(STATUS_FILE) and os.path.getsize(STATUS_FILE) > 0:
                            with open(STATUS_FILE, "r", encoding="utf-8") as rf:
                                try:
                                    status_data = json.load(rf)
                                except json.JSONDecodeError:
                                    pass
                        logging.info(
                            f"✔ Successfully switched to '{base_model_clean}' on port {new_port}!"
                        )

                        # Replay buffered query to fallback model if present
                        if auto_replay and active_query:
                            logging.info(
                                f"🔄 Smart Switch: Automatically replaying preserved query "
                                f"to fallback model on port {new_port}..."
                            )
                            replay_buffered_query(port=new_port, buffer_file=buffer_file)
                    else:
                        logging.error(
                            f"✖ Failed to launch fallback model '{base_model_clean}' "
                            f"on port {allocated_port}."
                        )

                    updated_status = True
                    break

            if updated_status:
                with open(STATUS_FILE, "w", encoding="utf-8") as f:
                    json.dump(status_data, f, indent=4)

        except Exception as e:
            logging.critical(f"Unexpected error in Smart Switch loop: {e}")

        time.sleep(check_interval)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_parser():
    parser = argparse.ArgumentParser(
        prog="Smartswitch",
        description=(
            "Lumina Smart Switch — monitors active LLM processes and automatically\n"
            "replaces a degraded model with a lighter fallback on the same port.\n\n"
            "Supports GPU VRAM tracking: if a model loads primarily into VRAM\n"
            "(RAM delta < --vram-delta-mb), VRAM is monitored instead of system RAM."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Backward-compatible positional args\n"
            "  python Smartswitch.py Qwen2.5-0.5B-Instruct-Q4_K_M 0.25\n\n"
            "  # Named flags — full control\n"
            "  python Smartswitch.py \\\n"
            "    --base-model Qwen2.5-0.5B-Instruct-Q4_K_M \\\n"
            "    --ram-allowance 0.30 --interval 1.5 \\\n"
            "    --tps-threshold 0.80 --vram-delta-mb 500 \\\n"
            "    --gpu-index 0 --kill-timeout 5 --socket-wait 2.0 \\\n"
            "    --settle-time 3.0 --init-timeout 30.0 --grace-period 10.0 \\\n"
            "    --log-level DEBUG\n\n"
            "  # Force RAM-only (disable VRAM auto-detection)\n"
            "  python Smartswitch.py --base-model MyModel --no-vram"
        ),
    )

    # Positional args — kept for backward compatibility, optional
    parser.add_argument(
        "base_model_pos",
        nargs="?",
        default=None,
        metavar="BASE_MODEL",
        help="Fallback model name (positional, backward compat — prefer --base-model)",
    )
    parser.add_argument(
        "ram_allowance_pos",
        nargs="?",
        type=float,
        default=None,
        metavar="RAM_ALLOWANCE",
        help="RAM/VRAM growth tolerance 0–1 (positional, backward compat — prefer --ram-allowance)",
    )

    # Named flags
    parser.add_argument(
        "--base-model",
        default="Qwen2.5-0.5B-Instruct-Q4_K_M",
        metavar="MODEL",
        help="Fallback model name (default: Qwen2.5-0.5B-Instruct-Q4_K_M)",
    )
    parser.add_argument(
        "--ram-allowance",
        type=float,
        default=0.25,
        metavar="N",
        help="Fractional RAM/VRAM growth tolerance above baseline (default: 0.25 = 25%%)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        metavar="S",
        help="Monitor loop sleep interval in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--tps-threshold",
        type=float,
        default=0.75,
        metavar="N",
        help="Fraction of baseline T/s below which switch triggers (default: 0.75 = <75%% of baseline)",
    )
    parser.add_argument(
        "--min-tps-samples",
        type=int,
        default=2,
        metavar="N",
        help="Min T/s log entries before degradation check activates (default: 2)",
    )
    parser.add_argument(
        "--kill-timeout",
        type=float,
        default=3.0,
        metavar="S",
        help="Seconds to wait for graceful termination before SIGKILL (default: 3.0)",
    )
    parser.add_argument(
        "--socket-wait",
        type=float,
        default=1.5,
        metavar="S",
        help="Seconds to wait after kill before relaunching on the same port (default: 1.5)",
    )
    parser.add_argument(
        "--vram-delta-mb",
        type=float,
        default=300.0,
        metavar="MB",
        help=(
            "If RAM growth after launch is below this (MB), model is GPU-loaded "
            "and VRAM is tracked instead of RAM (default: 300)"
        ),
    )
    parser.add_argument(
        "--no-vram",
        action="store_true",
        default=False,
        help="Disable automatic VRAM detection; always track system RAM",
    )
    parser.add_argument(
        "--gpu-index",
        type=int,
        default=0,
        metavar="N",
        help="GPU device index for VRAM queries on multi-GPU machines (default: 0)",
    )
    parser.add_argument(
        "--settle-time",
        type=float,
        default=3.0,
        metavar="S",
        help="Seconds to wait for memory stabilization during initialization (default: 3.0)",
    )
    parser.add_argument(
        "--init-timeout",
        type=float,
        default=30.0,
        metavar="S",
        help="Max seconds to wait for model ready signal during initialization (default: 30.0)",
    )
    parser.add_argument(
        "--grace-period",
        type=float,
        default=10.0,
        metavar="S",
        help="Seconds after initialization to ignore startup memory spikes (default: 10.0)",
    )
    parser.add_argument(
        "--buffer-file",
        default=QUERY_BUFFER_FILE,
        metavar="PATH",
        help="Path to query buffer file (default: data/query_buffer.json)",
    )
    parser.add_argument(
        "--no-auto-replay",
        action="store_true",
        default=False,
        help="Disable automatic replaying of buffered query to fallback model upon switch",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        metavar="LEVEL",
        help="Logging verbosity: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO)",
    )

    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    # Named flags take precedence; positionals are the backward-compat fallback
    base_model = args.base_model_pos if args.base_model_pos is not None else args.base_model
    ram_allowance = args.ram_allowance_pos if args.ram_allowance_pos is not None else args.ram_allowance

    runforever(
        base_model=base_model,
        ram_allowance=ram_allowance,
        check_interval=args.interval,
        tps_threshold=args.tps_threshold,
        min_tps_samples=args.min_tps_samples,
        kill_timeout=args.kill_timeout,
        socket_wait=args.socket_wait,
        vram_delta_mb=args.vram_delta_mb,
        no_vram=args.no_vram,
        gpu_index=args.gpu_index,
        log_level=args.log_level,
        settle_time=args.settle_time,
        init_timeout=args.init_timeout,
        grace_period=args.grace_period,
        buffer_file=args.buffer_file,
        auto_replay=not args.no_auto_replay,
    )
