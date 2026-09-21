# Lumina.py
"""
Lumina.py - Unified cross-platform CLI dispatcher for the Lumina AI toolchain.

Dynamic OS detection automatically resolves the appropriate bundled JRE and
bundled CPython runtimes for Windows, macOS, and Linux.

Enterprise UI/UX: Suppresses raw system noise (SLF4J, reflection warnings,
deprecation notices) from terminal stdout while recording full raw logs to logs/lumina.log.
"""

import os
import platform
import subprocess
import sys
import time
import re
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SYSTEM_OS = platform.system().lower()  # "windows", "darwin", "linux"

# Paths
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "lumina.log")

# ANSI Color Palette
CLR_BRAND = "\033[38;2;0;210;255m"  # Vibrant Cyan / Teal
CLR_PURPLE = "\033[38;2;160;32;240m"  # Deep Purple Accent
CLR_SUCCESS = "\033[38;2;46;204;113m"  # Emerald Green
CLR_WARN = "\033[38;2;241;196;15m"  # Warm Gold / Amber
CLR_ERROR = "\033[38;2;231;76;60m"  # Bright Coral Red
CLR_INFO = "\033[38;2;52;152;219m"  # Sky Blue
CLR_BOLD = "\033[1m"
CLR_DIM = "\033[2m"
CLR_RESET = "\033[0m"

# Regex for stripping ANSI escape sequences for file logging
ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

# Known background noise patterns to suppress from terminal output (logged to file only)
NOISE_PATTERNS = [
    r"SLF4J:",
    r"WARNING: A restricted method in java\.lang\.System",
    r"WARNING: java\.lang\.System::load",
    r"WARNING: Use --enable-native-access",
    r"WARNING: Restricted methods will be blocked",
    r"DeprecationWarning:",
    r"\[transformers\] Disabling PyTorch",
    r"\[transformers\] PyTorch was not found",
    r"UserWarning: Failed to initialize NumPy",
    r"A module that was compiled using NumPy",
    r"WARNING: There was an error checking the latest version of pip",
    r"WARNING: Target directory",
    r"To support both 1\.x and 2\.x versions of NumPy",
    r"If you are a user of the module, the easiest solution",
    r"We expect that some modules will need time",
    r"See http://www\.slf4j\.org/codes\.html",
    r"\[INFO\] Scanning for projects\.\.\.",
    r"\[INFO\] Building ",
    r"\[INFO\] Nothing to compile",
    r"Requirement already satisfied:",
    r"org\.slf4j\.impl\.StaticLoggerBinder",
    r"com\.sun\.jna\.Native",
]

# Core Python packages required by Lumina scripts
REQUIRED_PACKAGES = [
    "huggingface-hub<1.0.0",
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
    "transformers<4.45.0",
    "tokenizers",
    "onnxruntime",
    "numpy<2",
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


def strip_ansi(text):
    """Strips ANSI control codes for plain-text file logging."""
    return ANSI_ESCAPE.sub("", text)


def log_to_file(raw_line):
    """Appends raw timestamped output to logs/lumina.log quietly."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        clean_line = strip_ansi(raw_line).rstrip()
        if clean_line:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {clean_line}\n")
    except Exception:
        pass


def lumina_log(message, tag="Engine", level="INFO"):
    """Prints a branded Lumina status message to terminal AND logs to logs/lumina.log."""
    if level == "SUCCESS":
        badge = f"{CLR_SUCCESS}✔{CLR_RESET}"
        prefix = f"{CLR_BRAND}[Lumina {tag}]{CLR_RESET} {badge}"
    elif level == "WARN":
        badge = f"{CLR_WARN}⚠️{CLR_RESET}"
        prefix = f"{CLR_BRAND}[Lumina {tag}]{CLR_RESET} {badge}"
    elif level == "ERROR":
        badge = f"{CLR_ERROR}✖{CLR_RESET}"
        prefix = f"{CLR_BRAND}[Lumina {tag}]{CLR_RESET} {badge}"
    else:
        prefix = f"{CLR_BRAND}[Lumina {tag}]{CLR_RESET}"

    formatted_msg = f"{prefix} {message}"
    print(formatted_msg)
    sys.stdout.flush()
    log_to_file(f"[{level}] [{tag}] {message}")


def is_noise_line(line):
    """Returns True if the output line matches known noisy system/compiler/warning chatter."""
    for pattern in NOISE_PATTERNS:
        if re.search(pattern, line, re.IGNORECASE):
            return True
    return False


def format_subprocess_line(line, tag="Engine"):
    """Formats valid subprocess output with professional Lumina ANSI branding."""
    line_clean = line.strip()
    if not line_clean:
        return None

    # Lumina Web Server
    if "Lumina Web Server running locally!" in line_clean or "✨ Lumina Web Server" in line_clean:
        return f"{CLR_BRAND}[Lumina Server]{CLR_RESET} {CLR_SUCCESS}✨ Lumina Web Server is live and running locally!{CLR_RESET}"
    elif "Access Web Dashboard at:" in line_clean or "http://localhost:" in line_clean:
        url = line_clean.split("at:")[-1].strip() if "at:" in line_clean else line_clean
        return f"{CLR_BRAND}[Lumina Server]{CLR_RESET} {CLR_INFO}👉 Access Web Dashboard at: {CLR_BOLD}{url}{CLR_RESET}"
    elif "Failed to bind port" in line_clean:
        return f"{CLR_BRAND}[Lumina Server]{CLR_RESET} {CLR_WARN}Port conflict detected, retrying next port...{CLR_RESET}"

    # Benchmarks & Assessment
    elif "Calculated True Bandwidth:" in line_clean:
        return f"{CLR_BRAND}[Lumina Assess]{CLR_RESET} {CLR_SUCCESS}📊 {line_clean}{CLR_RESET}"
    elif "Estimated tokens/sec" in line_clean:
        return f"{CLR_BRAND}[Lumina Assess]{CLR_RESET} {CLR_INFO}⚡ {line_clean}{CLR_RESET}"
    elif "Raw Token/s Array:" in line_clean:
        return f"{CLR_BRAND}[Lumina Assess]{CLR_RESET} {CLR_DIM}{line_clean}{CLR_RESET}"

    # Downloader
    elif "Starting download for:" in line_clean:
        return f"{CLR_BRAND}[Lumina Downloader]{CLR_RESET} {CLR_INFO}📥 {line_clean}{CLR_RESET}"
    elif "From Repository:" in line_clean:
        return f"{CLR_BRAND}[Lumina Downloader]{CLR_RESET} {CLR_DIM}{line_clean}{CLR_RESET}"
    elif "Successfully downloaded to:" in line_clean:
        return f"{CLR_BRAND}[Lumina Downloader]{CLR_RESET} {CLR_SUCCESS}✔ {line_clean}{CLR_RESET}"

    # RAG & Reasoning
    elif "Loaded" in line_clean and "document" in line_clean:
        return f"{CLR_BRAND}[Lumina RAG]{CLR_RESET} {CLR_INFO}📄 {line_clean}{CLR_RESET}"
    elif "Created" in line_clean and "chunks" in line_clean:
        return f"{CLR_BRAND}[Lumina RAG]{CLR_RESET} {CLR_INFO}🧩 {line_clean}{CLR_RESET}"
    elif "Connecting to Qwen" in line_clean or "Loading existing vector store" in line_clean:
        return f"{CLR_BRAND}[Lumina RAG]{CLR_RESET} {CLR_INFO}🔗 {line_clean}{CLR_RESET}"
    elif "ANSWER:" in line_clean:
        return f"{CLR_BRAND}[Lumina RAG]{CLR_RESET} {CLR_SUCCESS}{CLR_BOLD}{line_clean}{CLR_RESET}"
    elif "SOURCES USED:" in line_clean:
        return f"{CLR_BRAND}[Lumina RAG]{CLR_RESET} {CLR_PURPLE}{line_clean}{CLR_RESET}"

    # ── Agentic pipeline output ────────────────────────────────────────────────
    elif "[AGENTIC]" in line_clean:
        return f"{CLR_BRAND}[Lumina Agentic]{CLR_RESET} {CLR_INFO}🤖 {line_clean}{CLR_RESET}"
    elif "[LOOP]" in line_clean:
        return f"{CLR_BRAND}[Lumina Agentic]{CLR_RESET} {CLR_INFO}🔄 {line_clean}{CLR_RESET}"
    elif "[LLM]" in line_clean and "Decision:" in line_clean:
        return f"{CLR_BRAND}[Lumina Agentic]{CLR_RESET} {CLR_PURPLE}💬 {line_clean}{CLR_RESET}"
    elif "[LLM]" in line_clean:
        return f"{CLR_BRAND}[Lumina Agentic]{CLR_RESET} {CLR_DIM}{line_clean}{CLR_RESET}"
    elif "[EXEC]" in line_clean and "Python:" in line_clean:
        return f"{CLR_BRAND}[Lumina Agentic]{CLR_RESET} {CLR_DIM}🐍 {line_clean}{CLR_RESET}"
    elif "[EXEC]" in line_clean and "Running:" in line_clean:
        return f"{CLR_BRAND}[Lumina Agentic]{CLR_RESET} {CLR_INFO}⚙️  {line_clean}{CLR_RESET}"
    elif "[EXEC]" in line_clean:
        return f"{CLR_BRAND}[Lumina Agentic]{CLR_RESET} {CLR_DIM}{line_clean}{CLR_RESET}"
    elif "[RESULT]" in line_clean:
        return f"{CLR_BRAND}[Lumina Agentic]{CLR_RESET} {CLR_SUCCESS}✔ {line_clean}{CLR_RESET}"
    elif "[SKIP]" in line_clean:
        return f"{CLR_BRAND}[Lumina Agentic]{CLR_RESET} {CLR_DIM}↷ {line_clean}{CLR_RESET}"
    elif "[ERROR]" in line_clean and "Agentic" in line_clean:
        return f"{CLR_BRAND}[Lumina Agentic]{CLR_RESET} {CLR_ERROR}✖ {line_clean}{CLR_RESET}"
    elif line_clean.startswith("RESULTS:") or line_clean.startswith("="):
        return f"{CLR_BRAND}[Lumina Agentic]{CLR_RESET} {CLR_SUCCESS}{CLR_BOLD}{line_clean}{CLR_RESET}"
    elif line_clean.startswith("Status:"):
        return f"{CLR_BRAND}[Lumina Agentic]{CLR_RESET} {CLR_SUCCESS}📋 {line_clean}{CLR_RESET}"
    elif line_clean.startswith("Iterations used:"):
        return f"{CLR_BRAND}[Lumina Agentic]{CLR_RESET} {CLR_INFO}🔢 {line_clean}{CLR_RESET}"
    elif line_clean.startswith("Result:"):
        return f"{CLR_BRAND}[Lumina Agentic]{CLR_RESET} {CLR_SUCCESS}{line_clean}{CLR_RESET}"
    # ──────────────────────────────────────────────────────────────────────────

    # Preserved Lumina formatting
    elif line_clean.startswith("[Lumina]"):
        content = line_clean[8:].strip()
        return f"{CLR_BRAND}[Lumina {tag}]{CLR_RESET} {content}"

    # General clean line
    return f"{CLR_BRAND}[Lumina {tag}]{CLR_RESET} {line_clean}"


def run_logged_process(cmd, cwd=PROJECT_ROOT, env=None, tag="Engine"):
    """
    Executes a subprocess while intercepting stdout/stderr.
    Filters raw noise from terminal while recording 100% of raw output to logs/lumina.log.
    """
    if env is None:
        env = os.environ.copy()

    # Force unbuffered Python output for real-time streaming
    env["PYTHONUNBUFFERED"] = "1"

    log_to_file(f"=== Command Execution Started: {' '.join(cmd)} ===")

    try:
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        for line in iter(process.stdout.readline, ""):
            if not line:
                break

            # 1. Record raw output line to lumina.log
            log_to_file(line)

            # 2. Suppress noise from terminal display
            if is_noise_line(line):
                continue

            # 3. Format & print clean output to terminal
            formatted = format_subprocess_line(line, tag=tag)
            if formatted:
                print(formatted)
                sys.stdout.flush()

        process.stdout.close()
        return_code = process.wait()

        log_to_file(f"=== Command Finished with Exit Code: {return_code} ===")
        return return_code

    except Exception as e:
        err_msg = f"Failed to execute process: {e}"
        log_to_file(f"[ERROR] {err_msg}")
        lumina_log(err_msg, tag=tag, level="ERROR")
        return 1


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

    return sys.executable, None


def get_bundled_site_packages():
    """Returns the site-packages directory inside the bundled Python env for the current OS."""
    os_type = detect_os()
    if os_type == "macos":
        return os.path.join(
            PROJECT_ROOT,
            "python-dependencies",
            "macos-intel",
            "lib",
            "python3.10",
            "site-packages",
        )
    elif os_type == "windows":
        return os.path.join(
            PROJECT_ROOT, "python-dependencies", "windows", "Lib", "site-packages"
        )
    else:
        return os.path.join(
            PROJECT_ROOT,
            "python-dependencies",
            "linux-intel",
            "lib",
            "python3.10",
            "site-packages",
        )


def get_pip_platform_flags():
    """Returns extra pip flags needed when cross-installing into a bundled env."""
    return []


def install_package(packages):
    """Installs one or more Python packages into the bundled Python env cleanly."""
    site_packages = get_bundled_site_packages()
    os.makedirs(site_packages, exist_ok=True)

    python_bin, _ = get_bundled_python()
    pip_flags = get_pip_platform_flags()

    lumina_log(f"Installing dependencies into bundled Python ({detect_os()})...", tag="Installer")
    lumina_log(f"Target location: {site_packages}", tag="Installer")
    print()

    pip_cmd = [
        python_bin,
        "-m",
        "pip",
        "install",
        "--target",
        site_packages,
        "--no-user",
    ] + pip_flags + packages
    result = run_logged_process(pip_cmd, tag="Installer")

    if result == 0:
        lumina_log("Successfully installed all requested packages!", tag="Installer", level="SUCCESS")
        return

    lumina_log("Bulk install encountered an issue. Retrying per package...", tag="Installer", level="WARN")
    successes = []
    failures = []
    for pkg in packages:
        lumina_log(f"Installing package: {pkg}...", tag="Installer")
        single_cmd = [
            python_bin,
            "-m",
            "pip",
            "install",
            "--target",
            site_packages,
            "--no-user",
        ] + pip_flags + [pkg]
        res = run_logged_process(single_cmd, tag="Installer")
        if res == 0:
            successes.append(pkg)
        else:
            failures.append(pkg)

    if successes:
        lumina_log(f"Successfully installed: {', '.join(successes)}", tag="Installer", level="SUCCESS")
    if failures:
        lumina_log(f"Failed to install: {', '.join(failures)}", tag="Installer", level="WARN")


def install_all_dependencies():
    """Installs all required Lumina Python dependencies into the bundled env."""
    lumina_log("Starting automated Lumina dependency installation...", tag="Installer")
    lumina_log(f"Packages required: {', '.join(REQUIRED_PACKAGES)}", tag="Installer")
    print()
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
        "description": "RAG vector store pipeline  [--file PATH, --port N, --chunk-size, --overlap, --k, --search-type, --db-dir, --force-rebuild]",
    },
    "--context": {
        "type": "python",
        "target": os.path.join(PROJECT_ROOT, "scripts", "rag.py"),
        "description": "RAG with context persistence  [--file PATH, --port N, --context, --embed, ...]",
    },
    "--embed": {
        "type": "python",
        "target": os.path.join(PROJECT_ROOT, "scripts", "rag.py"),
        "description": "Embeds stored conversation context into vector store",
    },
    "--agentic": {
        "type": "python",
        "target": os.path.join(PROJECT_ROOT, "scripts", "agentic_rag.py"),
        "description": "Autonomous multi-step agent: chains tools to complete tasks  [--query TEXT, --port N, --iterations N, --temperature N, --verbose]",
    },
    "--launch": {
        "type": "python",
        "target": os.path.join(PROJECT_ROOT, "scripts", "launch_model.py"),
        "description": "Launch a GGUF model via llamafile server  [--model, --port, --host, --startup-timeout, --max-attempts]",
    },
    "--switch": {
        "type": "python",
        "target": os.path.join(PROJECT_ROOT, "scripts", "Smartswitch.py"),
        "description": "Smart Switch watchdog: auto fallback + GPU VRAM tracking  [--base-model, --ram-allowance, --interval, --tps-threshold, --vram-delta-mb, --no-vram, --gpu-index, --log-level, ...]",
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

    lumina_log("Compiled Java binaries not found. Compiling Java sources...", tag="Java")
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
            res = run_logged_process(cmd, tag="Compiler")
            if res == 0:
                lumina_log("Java compilation completed successfully.", tag="Java", level="SUCCESS")
                return
        except Exception:
            pass

    try:
        res = run_logged_process(["mvn", "compile"], tag="Maven")
        if res == 0:
            lumina_log("Maven compilation completed successfully.", tag="Java", level="SUCCESS")
            return
    except Exception:
        pass


def run_java(target_class, extra_args):
    """Executes a Java main class using the bundled JRE with Lumina logging wrapper."""
    ensure_java_compiled()
    java_bin = get_bundled_jre()
    classpath = build_java_classpath()

    tag = target_class.split(".")[-1]
    cmd = [java_bin, "-cp", classpath, target_class] + extra_args

    lumina_log(f"Detected OS: {detect_os()} | JRE: {java_bin}", tag="Java")
    show_loading_animation(0.8, f"Preparing Lumina Java Context for {tag}")
    lumina_log(f"Launching {CLR_BOLD}{target_class}{CLR_RESET}...", tag=tag)
    print()

    code = run_logged_process(cmd, tag=tag)
    if code == 0:
        lumina_log(f"{tag} execution completed successfully. (Full log saved to {LOG_FILE})", tag=tag, level="SUCCESS")
    else:
        lumina_log(f"{tag} process exited with code {code}. (Full log saved to {LOG_FILE})", tag=tag, level="WARN")


def run_python(script_path, extra_args):
    """Executes a Python script using the bundled Python interpreter with Lumina logging wrapper."""
    python_bin, python_home = get_bundled_python()

    env = os.environ.copy()
    if python_home:
        env["PYTHONHOME"] = python_home

    script_name = os.path.basename(script_path)
    tag = script_name.replace(".py", "").capitalize()
    cmd = [python_bin, script_path] + extra_args

    lumina_log(f"Detected OS: {detect_os()} | Python: {python_bin}", tag="Python")
    show_loading_animation(0.8, f"Initializing Lumina Python Context for {script_name}")
    lumina_log(f"Executing {CLR_BOLD}{script_name}{CLR_RESET}...", tag=tag)
    print()

    code = run_logged_process(cmd, env=env, tag=tag)
    if code == 0:
        lumina_log(f"{script_name} execution completed successfully. (Full log saved to {LOG_FILE})", tag=tag, level="SUCCESS")
    else:
        lumina_log(f"{script_name} process exited with code {code}. (Full log saved to {LOG_FILE})", tag=tag, level="WARN")


def show_loading_animation(duration=1.2, text="Initializing Lumina Engine"):
    """Displays a smooth ANSI loading spinner."""
    chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    steps = int(duration / 0.1)
    for i in range(steps):
        sys.stdout.write(f"\r{CLR_BRAND}[Lumina]{CLR_RESET} {CLR_INFO}{chars[i % len(chars)]}{CLR_RESET} {text}...")
        sys.stdout.flush()
        time.sleep(0.1)
    sys.stdout.write(f"\r{CLR_BRAND}[Lumina]{CLR_RESET} {CLR_SUCCESS}✔{CLR_RESET} {text}... Done!      \n")
    sys.stdout.flush()


def print_help():
    """Displays the branded Lumina CLI dashboard and command list."""
    show_loading_animation(0.8, "Booting Lumina Core Engine")

    print(f"\n{CLR_BRAND}✧･ﾟ: *✧･ﾟ:* ✧･ﾟ: *✧･ﾟ:* ✧･ﾟ: *✧･ﾟ:* ✧･ﾟ: *✧･ﾟ:*{CLR_RESET}\n")
    print(
        f"{CLR_PURPLE}"
        + """
 ▒▒███                                   ▒▒▒                       
  ▒███        █████ ████ █████████████   ████  ████████    ██████  
  ▒███       ▒▒███ ▒███ ▒▒███▒▒███▒▒███ ▒▒███ ▒▒███▒▒███  ▒▒▒▒▒███ 
  ▒███        ▒███ ▒███  ▒███ ▒███ ▒███  ▒███  ▒███ ▒███   ███████ 
  ▒███      █ ▒███ ▒███  ▒███ ▒███ ▒███  ▒███  ▒███ ▒███  ███▒▒███ 
  ███████████ ▒▒████████ █████▒███ █████ █████ ████ █████▒▒████████
 ▒▒▒▒▒▒▒▒▒▒▒   ▒▒▒▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒ ▒▒▒▒▒ ▒▒▒▒▒ ▒▒▒▒ ▒▒▒▒▒  ▒▒▒▒▒▒▒▒ 
    """
        + f"{CLR_RESET}"
    )
    print(f"{CLR_BRAND}✧･ﾟ: *✧･ﾟ:* ✧･ﾟ: *✧･ﾟ:* ✧･ﾟ: *✧･ﾟ:* ✧･ﾟ: *✧･ﾟ:*{CLR_RESET}\n")

    print(f" {CLR_BOLD}Lumina AI Engine — Enterprise CLI Toolchain{CLR_RESET}")
    print(f" {CLR_DIM}‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾{CLR_RESET}")

    python_bin, _ = get_bundled_python()
    print(f" {CLR_BRAND}[Lumina]{CLR_RESET} {CLR_WARN}❖ Platform:{CLR_RESET}       {detect_os()}")
    print(f" {CLR_BRAND}[Lumina]{CLR_RESET} {CLR_WARN}❖ Bundled JRE:{CLR_RESET}    {get_bundled_jre()}")
    print(f" {CLR_BRAND}[Lumina]{CLR_RESET} {CLR_WARN}❖ Bundled Python:{CLR_RESET} {python_bin}")
    print(f" {CLR_BRAND}[Lumina]{CLR_RESET} {CLR_WARN}❖ Log File:{CLR_RESET}       {LOG_FILE}\n")

    print(f" {CLR_SUCCESS}Usage:{CLR_RESET} {CLR_BOLD}lumina <command> [args...]{CLR_RESET}\n")

    print(f" {CLR_SUCCESS}Available Lumina Commands:{CLR_RESET}")
    for key, info in COMMANDS.items():
        print(f"  {CLR_BRAND}{key:<18}{CLR_RESET} {CLR_DIM}→{CLR_RESET} {CLR_BOLD}{info['description']}{CLR_RESET}")
    print(f"\n{CLR_BRAND}✧･ﾟ: *✧･ﾟ:* ✧･ﾟ: *✧･ﾟ:* ✧･ﾟ: *✧･ﾟ:* ✧･ﾟ: *✧･ﾟ:*{CLR_RESET}\n")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h", "help"):
        print_help()
        sys.exit(0)
    elif sys.argv[1] not in COMMANDS:
        lumina_log(f"Unknown command: '{sys.argv[1]}'. See available commands below.", tag="CLI", level="WARN")
        print_help()
        sys.exit(1)

    command = sys.argv[1]
    extra_args = sys.argv[2:]
    entry = COMMANDS[command]

    if entry["type"] == "java":
        run_java(entry["target"], extra_args)
    elif entry["type"] == "python":
        if command in ("--context", "--embed") and command not in extra_args:
            extra_args = [command] + extra_args
        run_python(entry["target"], extra_args)
    elif entry["type"] == "builtin":
        if command == "--install":
            if not extra_args:
                lumina_log("Error: --install requires at least one package name.", tag="Installer", level="ERROR")
                print("  Usage: lumina --install <package1> [package2 ...]")
                sys.exit(1)
            install_package(extra_args)
        elif command == "--dependencies":
            install_all_dependencies()


if __name__ == "__main__":
    main()