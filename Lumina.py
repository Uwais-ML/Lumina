# Lumina.py
"""
Lumina.py - Unified cross-platform CLI dispatcher for the Lumina AI toolchain.

Dynamic OS detection automatically resolves the appropriate bundled JRE and
bundled CPython runtimes for Windows, macOS, and Linux.

Usage:
    lumina --models     -> Launches the LLM model store web server (LuminaWebServer)
    lumina --bench      -> Runs the hardware benchmark (Runit)
    lumina --assess     -> Runs the bandwidth/token predictor (SystemAssess)
    lumina --download   -> Runs the custom model downloader (downloadmodel)
    lumina --setup      -> Downloads base test models (download_base_models.py)
    lumina --rag        -> Runs the local RAG pipeline (rag.py)
    lumina --agentic    -> Runs the Agentic RAG pipeline (agentic_rag.py)
"""

import os
import platform
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SYSTEM_OS = platform.system().lower()  # "windows", "darwin", "linux"


def detect_os():
    """Returns normalized OS string: 'windows', 'macos', or 'linux'."""
    system = platform.system().lower()
    if "darwin" in system or "mac" in system:
        return "macos"
    elif system.startswith("win"):
        return "windows"
    elif "linux" in system:
        return "linux"
    return system


def get_bundled_jre():
    """Dynamically locates bundled Java executable based on OS detection."""
    os_type = detect_os()
    if os_type == "macos":
        target_dir = os.path.join(PROJECT_ROOT, "Jre", "Mac-intel")
        binary_name = "java"
    elif os_type == "windows":
        target_dir = os.path.join(PROJECT_ROOT, "Jre", "Windows")
        binary_name = "java.exe"
    else:
        target_dir = os.path.join(PROJECT_ROOT, "Jre", "Linux")
        binary_name = "java"

    if os.path.exists(target_dir):
        for root, _, files in os.walk(target_dir):
            if binary_name in files:
                full_path = os.path.join(root, binary_name)
                if os_type == "windows" or os.access(full_path, os.X_OK):
                    return full_path

    # Fallback to system java if bundled JRE is not found
    return "java"


def get_bundled_python():
    """Dynamically locates bundled Python interpreter and PYTHONHOME based on OS detection."""
    os_type = detect_os()
    if os_type == "macos":
        home_dir = os.path.join(PROJECT_ROOT, "python-dependencies", "macos-intel")
        bin_path = os.path.join(home_dir, "bin", "python3")
    elif os_type == "windows":
        home_dir = os.path.join(PROJECT_ROOT, "python-dependencies", "windows")
        bin_path = os.path.join(home_dir, "python.exe")
    else:
        home_dir = os.path.join(PROJECT_ROOT, "python-dependencies", "linux-intel")
        bin_path = os.path.join(home_dir, "bin", "python3")

    if os.path.exists(bin_path):
        return bin_path, home_dir

    # Fallback to system python interpreter
    return sys.executable, None


def build_java_classpath():
    """Builds self-contained classpath from target/classes, lib/*.jar, and target/*.jar."""
    cp_entries = []

    target_classes = os.path.join(PROJECT_ROOT, "target", "classes")
    if os.path.exists(target_classes):
        cp_entries.append(target_classes)

    lib_dir = os.path.join(PROJECT_ROOT, "lib")
    if os.path.exists(lib_dir):
        for f in os.listdir(lib_dir):
            if f.endswith(".jar"):
                cp_entries.append(os.path.join(lib_dir, f))

    target_dir = os.path.join(PROJECT_ROOT, "target")
    if os.path.exists(target_dir):
        for f in os.listdir(target_dir):
            if f.endswith(".jar"):
                cp_entries.append(os.path.join(target_dir, f))

    sep = ";" if detect_os() == "windows" else ":"
    return sep.join(cp_entries)


# Command registry mapping CLI arguments to target classes or python scripts
COMMANDS = {
    "--models": {
        "type": "java",
        "target": "lumina.LuminaWebServer",
        "description": "Launches the LLM model store web server",
    },
    "--bench": {
        "type": "java",
        "target": "lumina.Runit",
        "description": "Runs hardware benchmark across local LLM models",
    },
    "--assess": {
        "type": "java",
        "target": "lumina.SystemAssess",
        "description": "Estimates bandwidth and tokens/sec for target models",
    },
    "--download": {
        "type": "java",
        "target": "lumina.downloadmodel",
        "description": "Downloads custom LLM model by ID from HuggingFace",
    },
    "--setup": {
        "type": "python",
        "target": os.path.join(PROJECT_ROOT, "scripts", "download_base_models.py"),
        "description": "Downloads base GGUF models",
    },
    "--rag": {
        "type": "python",
        "target": os.path.join(PROJECT_ROOT, "scripts", "rag.py"),
        "description": "Runs the local RAG vector store pipeline",
    },
    "--agentic": {
        "type": "python",
        "target": os.path.join(PROJECT_ROOT, "scripts", "agentic_rag.py"),
        "description": "Runs the Agentic RAG reasoning pipeline",
    },
    "--launch": {
        "type": "python",
        "target": os.path.join(PROJECT_ROOT, "scripts", "launch_model.py"),
        "description": "Launches a specific GGUF model via llamafile server",
    },
}


def ensure_java_compiled():
    """Ensures compiled Java classes or lumina.jar exist; attempts automatic build if missing."""
    target_classes = os.path.join(PROJECT_ROOT, "target", "classes")
    lumina_jar = os.path.join(PROJECT_ROOT, "lib", "lumina.jar")

    if os.path.exists(lumina_jar) or os.path.exists(target_classes):
        return

    print("[Lumina] Compiled Java classes/JAR not found. Attempting automatic build...")
    src_dir = os.path.join(PROJECT_ROOT, "src", "java")
    if not os.path.exists(src_dir):
        return

    os.makedirs(target_classes, exist_ok=True)
    lib_dir = os.path.join(PROJECT_ROOT, "lib")
    lib_jars = []
    if os.path.exists(lib_dir):
        for f in os.listdir(lib_dir):
            if f.endswith(".jar") and f != "lumina.jar":
                lib_jars.append(os.path.join(lib_dir, f))

    sep = ";" if detect_os() == "windows" else ":"
    cp = sep.join(lib_jars)

    java_files = []
    for root, _, files in os.walk(src_dir):
        for f in files:
            if f.endswith(".java"):
                java_files.append(os.path.join(root, f))

    if java_files:
        try:
            cmd = ["javac", "-d", target_classes]
            if cp:
                cmd.extend(["-cp", cp])
            cmd.extend(java_files)
            res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
            if res.returncode == 0:
                print("[Lumina] Java source compilation succeeded.")
                return
        except Exception:
            pass

    try:
        res = subprocess.run(["mvn", "compile"], cwd=PROJECT_ROOT, capture_output=True, text=True)
        if res.returncode == 0:
            print("[Lumina] Maven compilation succeeded.")
            return
    except Exception:
        pass


def run_java(target_class, extra_args):
    """Executes a Java main class using the dynamically resolved bundled JRE."""
    ensure_java_compiled()
    java_bin = get_bundled_jre()
    classpath = build_java_classpath()

    cmd = [java_bin, "-cp", classpath, target_class] + extra_args
    print(f"[Lumina] OS: {detect_os()} | Runtime: {java_bin}")
    print(f"[Lumina] Executing Java class: {target_class}\n")

    subprocess.run(cmd, cwd=PROJECT_ROOT, check=False)


def run_python(script_path, extra_args):
    """Executes a Python script using the dynamically resolved bundled Python interpreter."""
    python_bin, python_home = get_bundled_python()

    env = os.environ.copy()
    if python_home:
        env["PYTHONHOME"] = python_home

    cmd = [python_bin, script_path] + extra_args
    print(f"[Lumina] OS: {detect_os()} | Runtime: {python_bin}")
    print(f"[Lumina] Executing Python script: {os.path.basename(script_path)}\n")

    subprocess.run(cmd, cwd=PROJECT_ROOT, env=env, check=False)


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("=================================================")
        print(" Lumina AI Engine — Dynamic CLI Runner")
        print("=================================================")
        print(f" Detected OS: {detect_os()}")
        print(f" Bundled JRE: {get_bundled_jre()}")
        python_bin, _ = get_bundled_python()
        print(f" Bundled Python: {python_bin}")
        print("\nUsage: lumina <command> [args...]")
        print("\nAvailable commands:")
        for key, info in COMMANDS.items():
            print(f"  {key:<12} -> {info['description']}")
        print("=================================================")
        sys.exit(1)

    command = sys.argv[1]
    extra_args = sys.argv[2:]
    entry = COMMANDS[command]

    if entry["type"] == "java":
        run_java(entry["target"], extra_args)
    elif entry["type"] == "python":
        run_python(entry["target"], extra_args)


if __name__ == "__main__":
    main()