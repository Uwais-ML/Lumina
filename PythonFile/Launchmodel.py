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
            print("Usage: python3 Launchmodel.py <ModelName>")
            return
        Modelname = sys.argv[1]

    path = "src/main/java/com/example/LLMs/" + Modelname + ".gguf"
    pathtollama = "src/main/java/com/example/resources/Llamafile/"
    llamaname = "llamafile-0.10.4-thin"

    try:
        # Cross-platform adjustments
        if os.name == "nt":
            path = path.replace("/", "\\")
            pathtollama = pathtollama.replace("/", "\\")
            llamaname += ".exe"
        else:
            os.chmod(f"{pathtollama}{llamaname}", 0o755)

        if os.path.exists(path):
            allocated_port = find_free_port()
            llamafile_full_path = f"{pathtollama}{llamaname}"

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
                    cmd_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
            else:
                shell_cmd = f"'{llamafile_full_path}' --server --host 127.0.0.1 --port {allocated_port}  -m '{path}'"
                process = subprocess.Popen(
                    ["sh", "-c", shell_cmd],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

            time.sleep(2)

            if process.poll() is not None:
                stdout, stderr = process.communicate()
                print(f"[!] Server failed to start. Error log:\n{stderr}")
            else:
                print(f"[+] Success! Llamafile is live in the background.")
                print(f"[+] API Endpoint: http://127.0.0.1:{allocated_port}/v1")
                print(f"[+] Background PID: {process.pid}")
        else:
            print(f"[!] Error: GGUF model file not found at: {path}")

    except Exception as e:
        print(f"Error occurred: {e}")
def youchoose():
    path = "src/main/java/com/example/LLMs/"
    
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
    youchoose()
