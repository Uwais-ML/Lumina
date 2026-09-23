import os
import socket
import subprocess
import sys
import time
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def launchmodel(Modelname=None, port=None, host="127.0.0.1", startup_timeout=30.0, max_attempts=5):
    """
    Launch a GGUF model via llamafile server.

    Parameters
    ----------
    Modelname        : str   — Model name (with or without .gguf extension)
    port             : int   — Port to bind to (auto-selects a free port if None)
    host             : str   — Host address to bind to (default: 127.0.0.1)
    startup_timeout  : float — Seconds to wait for server ready signal (default: 30.0)
    max_attempts     : int   — Number of port-finding retry attempts (default: 5)
    """

    if Modelname is None:
        if len(sys.argv) < 2:
            print("[!] Error: Missing model name argument.")
            print("Usage: python3 launch_model.py <ModelName> [port]")
            return None
        Modelname = sys.argv[1]

    if port is None and len(sys.argv) > 2:
        try:
            port = int(sys.argv[2])
        except ValueError:
            port = None

    # Resolve project root from this script's location (scripts/ is one level deep)
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

    model_file = Modelname if Modelname.endswith(".gguf") else Modelname + ".gguf"
    base_model_name = Modelname[:-5] if Modelname.endswith(".gguf") else Modelname
    path = os.path.join(PROJECT_ROOT, "models", model_file)
    pathtollama = os.path.join(PROJECT_ROOT, "resources", "llamafile")
    llamaname = "llamafile-0.10.4-thin"

    try:
        # Cross-platform adjustments
        if os.name == "nt":
            exe_path = os.path.join(pathtollama, llamaname + ".exe")
            bare_path = os.path.join(pathtollama, llamaname)
            if os.path.exists(exe_path):
                llamaname += ".exe"
            elif not os.path.exists(bare_path):
                print(f"[!] Error: Llamafile binary not found at: {exe_path} or {bare_path}")
                return None
        else:
            llama_bin = os.path.join(pathtollama, llamaname)
            if os.path.exists(llama_bin):
                os.chmod(llama_bin, 0o755)

        llamafile_full_path = os.path.join(pathtollama, llamaname)

        if not os.path.exists(path):
            print(f"[!] Error: GGUF model file not found at: {path}")
            return None

        log_dir = os.path.join(PROJECT_ROOT, "logs")
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        log_file_path = os.path.join(log_dir, f"llamafile_{base_model_name}.log")

        # Retry loop for port allocation if specific port is busy
        poll_steps = max(1, int(startup_timeout / 0.2))
        for attempt in range(max_attempts):
            allocated_port = int(port) if (port is not None and attempt == 0) else find_free_port()
            log_file = open(log_file_path, "w")

            if os.name == "nt":
                cmd_args = [
                    llamafile_full_path,
                    "--server",
                    "--host",
                    host,
                    "--port",
                    str(allocated_port),
                    "-m",
                    path,
                ]
                process = subprocess.Popen(
                    cmd_args, stdout=log_file, stderr=subprocess.STDOUT, text=True
                )
            else:
                shell_cmd = f"'{llamafile_full_path}' --server --host {host} --port {allocated_port} -m '{path}'"
                process = subprocess.Popen(
                    ["sh", "-c", shell_cmd],
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,

                )

            # Wait up to startup_timeout for server startup
            started = False
            ready_markers = ("server is listening", "HTTP server listening", "model loaded", "all slots are idle")
            for _ in range(poll_steps):
                time.sleep(0.2)
                if process.poll() is not None:
                    # Check log for port binding failure
                    log_file.close()
                    with open(log_file_path, "r", encoding="utf-8", errors="ignore") as rf:
                        err_content = rf.read()
                        if "couldn't bind" in err_content or "Address already in use" in err_content:
                            break  # retry on next port
                    break
                else:
                    # Check if server listening message appeared in log
                    with open(log_file_path, "r", encoding="utf-8", errors="ignore") as rf:
                        log_content = rf.read()
                        if any(marker in log_content for marker in ready_markers):
                            started = True
                            break

            if started or process.poll() is None:
                if not started:
                    print(f"[*] Model warming up (PID: {process.pid})")
                print(f"[+] {base_model_name} · :{allocated_port} · PID {process.pid}")
                try:
                    import urllib.request, json
                    data = json.dumps({"port": allocated_port}).encode('utf-8')
                    req = urllib.request.Request("http://127.0.0.1:8080/api/modelport", data=data, headers={'Content-Type': 'application/json'})
                    urllib.request.urlopen(req, timeout=2)
                except Exception:
                    pass

                try:
                    import Smartswitch
                    Smartswitch.raminitilization(
                        base_model_name,
                        process.pid,
                        port=allocated_port,
                        log_file=log_file_path,
                        init_timeout=startup_timeout,
                    )
                except Exception:
                    pass

                return {"pid": process.pid, "port": allocated_port, "process": process, "model": base_model_name, "log_file": log_file_path}

        print(f"[!] Server failed to start after multiple attempts. See error log: {log_file_path}")
        return None

    except Exception as e:
        print(f"Error occurred: {e}")
        return None


def youchoose():
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
    path = os.path.join(PROJECT_ROOT, "models")
    if os.path.exists(path):
        for filename in os.listdir(path):
            if filename.endswith(".gguf"):
                b_index = filename.find('B')

                if b_index != -1:
                    param = ""

                    for i in range(b_index, -1, -1):
                        if filename[i] == "-":
                            break
                        param = filename[i] + param

                    print(f"Extracted parameter: {param}")


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="launch_model",
        description="Lumina Model Launcher — starts a GGUF model via llamafile server.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Backward-compatible positional args\n"
            "  python launch_model.py Qwen2.5-0.5B-Instruct-Q4_K_M 8080\n\n"
            "  # Named flags — full control\n"
            "  python launch_model.py --model Qwen2.5-0.5B-Instruct-Q4_K_M \\\n"
            "    --port 8080 --host 127.0.0.1 --startup-timeout 10.0 --max-attempts 3"
        ),
    )

    # Positional args (backward compat)
    parser.add_argument(
        "model_pos",
        nargs="?",
        default=None,
        metavar="MODEL",
        help="GGUF model name (positional, backward compat — prefer --model)",
    )
    parser.add_argument(
        "port_pos",
        nargs="?",
        type=int,
        default=None,
        metavar="PORT",
        help="Port to bind to (positional, backward compat — prefer --port)",
    )

    # Named flags
    parser.add_argument(
        "--model",
        default="Llama-3.2-1B-Instruct-Q4_K_M",
        metavar="MODEL",
        help="GGUF model name (default: Llama-3.2-1B-Instruct-Q4_K_M)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        metavar="PORT",
        help="Port to bind to (auto-selects a free port if None)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        metavar="HOST",
        help="Host address to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--startup-timeout",
        type=float,
        default=30.0,
        metavar="S",
        help="Seconds to wait for server ready signal (default: 30.0)",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=5,
        metavar="N",
        help="Number of port-finding retry attempts (default: 5)",
    )

    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    # Named flags take precedence; positionals are the backward-compat fallback
    model_name = args.model_pos if args.model_pos is not None else args.model
    port = args.port_pos if args.port_pos is not None else args.port

    launchmodel(
        Modelname=model_name,
        port=port,
        host=args.host,
        startup_timeout=args.startup_timeout,
        max_attempts=args.max_attempts,
    )
