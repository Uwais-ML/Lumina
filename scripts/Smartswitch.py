import os
import sys
import time
import json
import logging
import psutil

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


def killprocess(pid):
    """Gracefully terminates a process by PID, falling back to kill if needed."""
    try:
        if not psutil.pid_exists(pid):
            logging.info(f"Process with PID {pid} is already stopped.")
            return True
        process = psutil.Process(pid)
        process.terminate()
        try:
            process.wait(timeout=3)
        except (psutil.TimeoutExpired, psutil.NoSuchProcess):
            if process.is_running():
                process.kill()
                process.wait(timeout=2)
        logging.warning(f"Process with PID {pid} successfully terminated.")
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        logging.warning(f"Could not kill process {pid}: {e}")
        return False
    except Exception as e:
        logging.error(f"Error terminating process {pid}: {e}")
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


def raminitilization(model_name, pid, port=None):
    """Initializes and records model PID, allocated port, baseline RAM, and T/s in status.txt."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        time.sleep(1)
        if not psutil.pid_exists(pid):
            logging.error(f"Cannot initialize RAM: Process PID {pid} does not exist.")
            return

        proc_tracker = psutil.Process(pid)
        ram_bytes = proc_tracker.memory_info().rss
        ram_gb = ram_bytes / (1024 ** 3)

        status_data = {}
        if os.path.exists(STATUS_FILE) and os.path.getsize(STATUS_FILE) > 0:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                try:
                    status_data = json.load(f)
                except json.JSONDecodeError:
                    status_data = {}

        # Clean model name key
        key = model_name[:-5] if model_name.endswith(".gguf") else model_name

        status_data[key] = {
            "PID": int(pid),
            "PORT": int(port) if port is not None else None,
            "RAM": f"{ram_gb:.2f} GB",
            "T/s": 0.0
        }

        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(status_data, f, indent=4)

        logging.info(f"Model '{key}' initialized (PID: {pid}, Port: {port}, RAM: {ram_gb:.2f} GB)")
    except Exception as e:
        logging.error(f"Error saving model details for {model_name}: {e}")

# Alias for backward compatibility
ram_initialization = raminitilization


def get_model_log_file(model_name):
    """Returns the expected log file path for a model."""
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
                # Look for llamafile/llama.cpp eval time lines:
                # e.g., "eval time = 1200.00 ms / 24 tokens ( 50.00 ms per token, 20.00 tokens per second)"
                if "eval time" in line and "prompt eval time" not in line:
                    if "tokens per second" in line:
                        parts = line.split("tokens per second")[0].split()
                        if parts:
                            try:
                                tps = float(parts[-1].strip(" ,()"))
                                tps_history.append(tps)
                            except ValueError:
                                pass
                    elif "(" in line and ")" in line:
                        inside = line[line.find("(") + 1: line.find(")")]
                        segments = inside.split(",")
                        if len(segments) > 1:
                            try:
                                tps = float(segments[1].split()[0])
                                tps_history.append(tps)
                            except (ValueError, IndexError):
                                pass
    except Exception as e:
        logging.error(f"Error parsing log file {log_file_path}: {e}")

    return tps_history


def runforever(base_model="Qwen2.5-0.5B-Instruct-Q4_K_M", ram_allowance=0.25, check_interval=2.0):
    """
    Monitors active LLM processes. If memory inflates past the threshold or inference speed
    drops by > 25%, the degraded model is replaced by base_model on the exact same port.
    """
    logging.info(f"🚀 Smart Switch started. Fallback Model: '{base_model}' | RAM allowance: {ram_allowance * 100}%")

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

            # Safe iteration over items copy
            for key, info in list(status_data.items()):
                pid = info.get("PID")
                allocated_port = info.get("PORT")

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

                # 1. Check RAM usage
                mem_info = process.memory_info()
                ram_mb = mem_info.rss / (1024 * 1024)
                prev_ram_str = info.get("RAM", "0 GB").replace(" GB", "")
                try:
                    prev_ram_mb = float(prev_ram_str) * 1024
                except ValueError:
                    prev_ram_mb = ram_mb

                threshold_factor = (1.0 + ram_allowance) if ram_allowance <= 1.0 else 1.25
                threshold_mb = threshold_factor * prev_ram_mb

                ram_exceeded = ram_mb > threshold_mb
                if ram_exceeded:
                    logging.warning(
                        f"⚠️ High RAM detected for '{key}': current {ram_mb:.1f} MB exceeds baseline {prev_ram_mb:.1f} MB (threshold {threshold_mb:.1f} MB)"
                    )

                # 2. Check Tokens/sec performance degradation
                log_file = get_model_log_file(key)
                tps_history = parse_eval_tokens_per_second(log_file)
                perf_degraded = False

                if len(tps_history) >= 2:
                    baseline_tps = tps_history[0]
                    current_tps = tps_history[-1]
                    info["T/s"] = current_tps

                    # If current T/s has dropped below 75% of baseline
                    if baseline_tps > 0 and current_tps < (0.75 * baseline_tps):
                        logging.warning(
                            f"⚠️ Speed degradation detected for '{key}': baseline={baseline_tps:.2f} T/s -> current={current_tps:.2f} T/s (< 75%)"
                        )
                        perf_degraded = True

                # 3. Trigger Smart Switch if degraded or severe RAM inflation
                if (perf_degraded or (ram_exceeded and key != base_model_clean)) and key != base_model_clean:
                    logging.critical(
                        f"🚨 Triggering Smart Switch! Replacing '{key}' with fallback '{base_model_clean}' on port {allocated_port}..."
                    )

                    # Terminate degraded model process
                    killprocess(pid)
                    time.sleep(1.5)  # Allow OS socket to be fully released

                    # Launch fallback model on the exact same port
                    launch_result = launch_model.launchmodel(base_model, port=allocated_port)

                    del status_data[key]

                    if launch_result and "pid" in launch_result:
                        new_pid = launch_result["pid"]
                        new_port = launch_result["port"]
                        raminitilization(base_model_clean, new_pid, port=new_port)
                        logging.info(f"✔ Successfully switched to '{base_model_clean}' on same port {new_port}!")
                    else:
                        logging.error(f"✖ Failed to launch fallback model '{base_model_clean}' on port {allocated_port}.")

                    updated_status = True
                    break

            if updated_status:
                with open(STATUS_FILE, "w", encoding="utf-8") as f:
                    json.dump(status_data, f, indent=4)

        except Exception as e:
            logging.critical(f"Unexpected error in Smart Switch loop: {e}")

        time.sleep(check_interval)


if __name__ == "__main__":
    target_base = sys.argv[1] if len(sys.argv) > 1 else "Qwen2.5-0.5B-Instruct-Q4_K_M"
    allowance = float(sys.argv[2]) if len(sys.argv) > 2 else 0.25
    runforever(base_model=target_base, ram_allowance=allowance)
