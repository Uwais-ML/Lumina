import os
import socket
import subprocess
import sys
import time


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def launchmodel(Modelname=None):
    if Modelname is None:
        if len(sys.argv) < 2:
            print("[!] Error: Missing model name argument.")
            print("Usage: python3 launch_model.py <ModelName>")
            return
        Modelname = sys.argv[1]

    path = os.path.join("models", Modelname if Modelname.endswith(".gguf") else Modelname + ".gguf")
    pathtollama = os.path.join("resources", "llamafile")
    llamaname = "llamafile-0.10.4-thin"

    try:
        # Cross-platform adjustments
        if os.name == "nt":
            path = path.replace("/", "\\")
            pathtollama = pathtollama.replace("/", "\\")
            llamaname += ".exe"
        else:
            llama_bin = os.path.join(pathtollama, llamaname)
            if os.path.exists(llama_bin):
                os.chmod(llama_bin, 0o755)

        if os.path.exists(path):
            allocated_port = find_free_port()
            llamafile_full_path = os.path.join(pathtollama, llamaname)

            log_dir = "logs"
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
            log_file_path = os.path.join(log_dir, f"llamafile_{Modelname}.log")
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

            time.sleep(2)

            if process.poll() is not None:
                print(f"[!] Server failed to start. See error log: {log_file_path}")
            else:
                print(f"[+] Success! Llamafile is live in the background.")
                print(f"[+] API Endpoint: http://127.0.0.1:{allocated_port}/v1")
                print(f"[+] Background PID: {process.pid}")
                print(f"[+] Logs are being written to: {log_file_path}")
                try:
                    import urllib.request, json
                    data = json.dumps({"port": allocated_port}).encode('utf-8')
                    req = urllib.request.Request("http://127.0.0.1:8080/api/modelport", data=data, headers={'Content-Type': 'application/json'})
                    urllib.request.urlopen(req, timeout=2)
                except Exception as err:
                    print(f"[~] Could not notify web server on port 8080: {err}")
        else:
            print(f"[!] Error: GGUF model file not found at: {path}")

    except Exception as e:
        print(f"Error occurred: {e}")


def youchoose():
    path = "models/"
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
        launchmodel(sys.argv[1])
    else:
        launchmodel("Phi-3.5-mini-instruct-Q4_K_M")
