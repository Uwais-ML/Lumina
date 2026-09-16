# Lumina.py
"""
Lumina.py - Unified cross-platform CLI dispatcher for the Lumina AI toolchain.

Dynamic OS detection automatically resolves the appropriate bundled JRE and
bundled CPython runtimes for Windows, macOS, and Linux.

Usage:
    lumina --models               -> Launches the LLM model store web server (LuminaWebServer)
    lumina --bench                -> Runs the hardware benchmark (Runit)
    lumina --assess               -> Runs the bandwidth/token predictor (SystemAssess)
    lumina --download             -> Runs the custom model downloader (downloadmodel)
    lumina --setup                -> Downloads base test models (download_base_models.py)
    lumina --rag                  -> Runs the local RAG pipeline (rag.py)
    lumina --agentic              -> Runs the Agentic RAG pipeline (agentic_rag.py)
    lumina --install <pkg ...>    -> Installs Python package(s) into the bundled Python env
    lumina --dependencies         -> Installs ALL required Python dependencies automatically
"""

import os
import platform
import subprocess
import sys
import time


PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SYSTEM_OS = platform.system().lower()  # "windows", "darwin", "linux"

# Core Python packages required by Lumina scripts (no torch / no heavy ML frameworks)
REQUIRED_PACKAGES = [
    "huggingface-hub",
    "langchain",
    "langchain-community",
    "langchain-text-splitters",
    "langchain-chroma",
    "langchain-huggingface",
    "langchain-openai",
    "langchain-core",
    "chromadb",
    "sentence-transformers",
    "psutil",
    "pydantic",
    "requests",
    "transformers",
    "tokenizers",
    "onnxruntime",
    "numpy",
    "tqdm",
    "tiktoken",
    "openai",
    "rich",
    "python-dotenv",
    "pyyaml",
    "regex",
    "safetensors",
    "pillow",
]


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


def get_bundled_site_packages():
    """Returns the site-packages directory inside the bundled Python env for the current OS."""
    os_type = detect_os()
    if os_type == "macos":
        return os.path.join(PROJECT_ROOT, "python-dependencies", "macos-intel",
                            "lib", "python3.10", "site-packages")
    elif os_type == "windows":
        return os.path.join(PROJECT_ROOT, "python-dependencies", "windows",
                            "Lib", "site-packages")
    else:
        return os.path.join(PROJECT_ROOT, "python-dependencies", "linux-intel",
                            "lib", "python3.10", "site-packages")


def get_pip_platform_flags():
    """
    Returns extra pip flags needed when cross-installing into a bundled env.
    When running ON the target OS the bundled python's pip is used directly (no cross flags needed).
    """
    # When running on the native OS, we do not need cross-platform restriction flags
    return []


def install_package(packages):
    """
    Installs one or more Python packages into the bundled Python env for the current OS.
    Automatically selects the correct --target path.
    Installs packages cleanly and reports per-package status.
    """
    site_packages = get_bundled_site_packages()
    os.makedirs(site_packages, exist_ok=True)

    python_bin, _ = get_bundled_python()
    pip_flags = get_pip_platform_flags()

    print(f"[Lumina] Installing into bundled Python ({detect_os()})...")
    print(f"[Lumina] Target: {site_packages}\n")

    # First attempt bulk install
    pip_cmd = [python_bin, "-m", "pip", "install", "--target", site_packages, "--no-user"] + pip_flags + packages
    result = subprocess.run(pip_cmd, cwd=PROJECT_ROOT)

    if result.returncode == 0:
        print(f"\n[Lumina] ✓ Successfully installed all requested packages!")
        return

    print(f"\n[Lumina] Bulk install encountered an issue. Falling back to individual package installation...")
    successes = []
    failures = []
    for pkg in packages:
        print(f"\n[Lumina] Installing: {pkg}...")
        single_cmd = [python_bin, "-m", "pip", "install", "--target", site_packages, "--no-user"] + pip_flags + [pkg]
        res = subprocess.run(single_cmd, cwd=PROJECT_ROOT)
        if res.returncode == 0:
            successes.append(pkg)
        else:
            failures.append(pkg)

    if successes:
        print(f"\n[Lumina] ✓ Successfully installed: {', '.join(successes)}")
    if failures:
        print(f"[Lumina] ⚠️ Failed to install optional/incompatible packages: {', '.join(failures)}")


def install_all_dependencies():
    """Installs all required Lumina Python dependencies into the bundled env."""
    print("[Lumina] Installing all required Python dependencies...")
    print(f"[Lumina] Packages: {', '.join(REQUIRED_PACKAGES)}\n")
    install_package(REQUIRED_PACKAGES)


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
    "--install": {
        "type": "builtin",
        "description": "Installs Python package(s) into the bundled Python env  [usage: --install <pkg ...>]",
    },
    "--dependencies": {
        "type": "builtin",
        "description": "Installs ALL required Python dependencies into the bundled env",
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
    show_loading_animation(0.8, f"Preparing Java Environment for {target_class}")
    print(f"\033[92m[Lumina]\033[0m Executing Java class: \033[1m{target_class}\033[0m\n")

    subprocess.run(cmd, cwd=PROJECT_ROOT, check=False)


def run_python(script_path, extra_args):
    """Executes a Python script using the dynamically resolved bundled Python interpreter."""
    python_bin, python_home = get_bundled_python()

    env = os.environ.copy()
    if python_home:
        env["PYTHONHOME"] = python_home

    cmd = [python_bin, script_path] + extra_args
    print(f"[Lumina] OS: {detect_os()} | Runtime: {python_bin}")
    show_loading_animation(0.8, f"Initializing Python Context for {os.path.basename(script_path)}")
    print(f"\033[92m[Lumina]\033[0m Executing Python script: \033[1m{os.path.basename(script_path)}\033[0m\n")

    subprocess.run(cmd, cwd=PROJECT_ROOT, env=env, check=False)



def show_loading_animation(duration=1.5, text="Initializing Lumina Engine"):
    chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    steps = int(duration / 0.1)
    for i in range(steps):
        sys.stdout.write(f"\r\033[96m{chars[i % len(chars)]}\033[0m {text}...")
        sys.stdout.flush()
        time.sleep(0.1)
    sys.stdout.write(f"\r\033[92m✔\033[0m {text}... Done!      \n")
    sys.stdout.flush()

def print_help():
    show_loading_animation(1.0, "Booting Core Systems")
    
    # ANSI Colors
    c_cyan = "\033[96m"
    c_blue = "\033[94m"
    c_green = "\033[92m"
    c_magenta = "\033[95m"
    c_yellow = "\033[93m"
    c_white = "\033[1m"  # Bold default instead of forced white
    c_gray = "\033[0m"   # Default text instead of hard-to-read gray
    c_reset = "\033[0m"

    print(f"\n{c_cyan}✧･ﾟ: *✧･ﾟ:* ✧･ﾟ: *✧･ﾟ:* ✧･ﾟ: *✧･ﾟ:* ✧･ﾟ: *✧･ﾟ:*{c_reset}\n")
    print(f"{c_magenta}" + """
 ▒▒███                                   ▒▒▒                       
  ▒███        █████ ████ █████████████   ████  ████████    ██████  
  ▒███       ▒▒███ ▒███ ▒▒███▒▒███▒▒███ ▒▒███ ▒▒███▒▒███  ▒▒▒▒▒███ 
  ▒███        ▒███ ▒███  ▒███ ▒███ ▒███  ▒███  ▒███ ▒███   ███████ 
  ▒███      █ ▒███ ▒███  ▒███ ▒███ ▒███  ▒███  ▒███ ▒███  ███▒▒███ 
  ███████████ ▒▒████████ █████▒███ █████ █████ ████ █████▒▒████████
 ▒▒▒▒▒▒▒▒▒▒▒   ▒▒▒▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒ ▒▒▒▒▒  ▒▒▒▒▒▒▒▒ 
    """ + f"{c_reset}")
    print(f"{c_cyan}✧･ﾟ: *✧･ﾟ:* ✧･ﾟ: *✧･ﾟ:* ✧･ﾟ: *✧･ﾟ:* ✧･ﾟ: *✧･ﾟ:*{c_reset}\n")

    print(f" {c_white}Lumina AI Engine — Dynamic CLI Runner{c_reset}")
    print(f" {c_gray}‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾{c_reset}")
    
    print(f" {c_yellow}❖ Detected OS:{c_reset}     {detect_os()}")
    print(f" {c_yellow}❖ Bundled JRE:{c_reset}    {get_bundled_jre()}")
    python_bin, _ = get_bundled_python()
    print(f" {c_yellow}❖ Bundled Python:{c_reset} {python_bin}\n")
    
    print(f" {c_green}Usage:{c_reset} {c_white}lumina <command> [args...]{c_reset}\n")
    
    print(f" {c_green}Available commands:{c_reset}")
    for key, info in COMMANDS.items():
        print(f"  {c_cyan}{key:<16}{c_reset} {c_gray}→{c_reset} {c_white}{info['description']}{c_reset}")
    print(f"\n{c_cyan}✧･ﾟ: *✧･ﾟ:* ✧･ﾟ: *✧･ﾟ:* ✧･ﾟ: *✧･ﾟ:* ✧･ﾟ: *✧･ﾟ:*{c_reset}\n")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print_help()
        sys.exit(1)

    command = sys.argv[1]
    extra_args = sys.argv[2:]
    entry = COMMANDS[command]

    if entry["type"] == "java":
        run_java(entry["target"], extra_args)
    elif entry["type"] == "python":
        run_python(entry["target"], extra_args)
    elif entry["type"] == "builtin":
        if command == "--install":
            if not extra_args:
                print("[Lumina] Error: --install requires at least one package name.")
                print("  Usage: lumina --install <package1> [package2 ...]")
                sys.exit(1)
            install_package(extra_args)
        elif command == "--dependencies":
            install_all_dependencies()


if __name__ == "__main__":
    main()