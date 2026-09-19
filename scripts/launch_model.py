import os
import socket
import subprocess
import sys
import time


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def launchmodel(Modelname=None, port=None):
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
        max_attempts = 5
        for attempt in range(max_attempts):
            allocated_port = int(port) if (port is not None and attempt == 0) else find_free_port()
            log_file = open(log_file_path, "w")

            if os.name == "nt":
                cmd_args = [
                    llamafile_full_path,
                    "--server",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(allocated_port),
                    "--nobrowser",
                    "-m",
                    path,
                ]
                process = subprocess.Popen(
                    cmd_args, stdout=log_file, stderr=subprocess.STDOUT, text=True
                )
            else:
                shell_cmd = f"'{llamafile_full_path}' --server --host 127.0.0.1 --port {allocated_port} -m '{path}'"
                process = subprocess.Popen(
                    ["sh", "-c", shell_cmd],
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                )

            # Wait up to 5 seconds for server startup
            started = False
            for _ in range(25):
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
                        if "server is listening" in log_content or "model loaded" in log_content:
                            started = True
                            break

            if started or process.poll() is None:
                print(f"[+] Success! Llamafile is live in the background.")
                print(f"[+] API Endpoint: http://127.0.0.1:{allocated_port}/v1")
                print(f"[+] Background PID: {process.pid}")
                print(f"[+] Logs are being written to: {log_file_path}")
                try:
                    import urllib.request, json
                    data = json.dumps({"port": allocated_port}).encode('utf-8')
                    req = urllib.request.Request("http://127.0.0.1:8080/api/modelport", data=data, headers={'Content-Type': 'application/json'})
                    urllib.request.urlopen(req, timeout=2)
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


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_port = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else None
        launchmodel(sys.argv[1], port=target_port)
    else:
        launchmodel("Llama-3.2-1B-Instruct-Q4_K_M")
