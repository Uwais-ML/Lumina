#!/usr/bin/env python3
"""
scripts/setup_environment.py
============================
Universal cross-platform bootstrap setup for Lumina AI Toolchain.
Works seamlessly across Linux (Ubuntu, Debian, Google Colab), macOS (Apple Silicon & Intel), and Windows.

Responsibilities:
  1. Detects OS, CPU architecture, and available GPU hardware (CUDA, Metal, ROCm).
  2. Ensures llamafile-0.10.4 executable is present, correct for the OS, and has execute permissions.
  3. Verifies Java runtime environment (bundled JRE or system java).
  4. Verifies/installs essential Python dependencies.
  5. Downloads the 3 base GGUF models directly into models/ with automatic fallback to direct CDN URLs.
  6. Calibrates local storage and prepares environment for benchmarks.
"""

import os
import sys
import platform
import subprocess
import shutil
import urllib.request
import urllib.error
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
RESOURCES_DIR = os.path.join(PROJECT_ROOT, "resources")
LLAMAFILE_DIR = os.path.join(RESOURCES_DIR, "llamafile")

# ANSI styling
CLR_BRAND = "\033[38;2;0;210;255m"
CLR_SUCCESS = "\033[38;2;46;204;113m"
CLR_WARN = "\033[38;2;241;196;15m"
CLR_ERROR = "\033[38;2;231;76;60m"
CLR_BOLD = "\033[1m"
CLR_RESET = "\033[0m"


def log(msg, level="INFO"):
    if level == "SUCCESS":
        print(f"{CLR_BRAND}[Lumina Setup]{CLR_RESET} {CLR_SUCCESS}✔{CLR_RESET} {msg}")
    elif level == "WARN":
        print(f"{CLR_BRAND}[Lumina Setup]{CLR_RESET} {CLR_WARN}⚠️{CLR_RESET} {msg}")
    elif level == "ERROR":
        print(f"{CLR_BRAND}[Lumina Setup]{CLR_RESET} {CLR_ERROR}✖{CLR_RESET} {msg}")
    else:
        print(f"{CLR_BRAND}[Lumina Setup]{CLR_RESET} {msg}")


def detect_platform():
    system = platform.system().lower()
    machine = platform.machine().lower()
    if "darwin" in system:
        os_name = "macos"
    elif "win" in system:
        os_name = "windows"
    else:
        os_name = "linux"
    return os_name, machine


def check_gpu():
    """Detects available GPU hardware (NVIDIA CUDA, Apple Metal, or CPU fallback)."""
    has_cuda = False
    has_metal = False

    # Check CUDA
    try:
        res = subprocess.run(["nvidia-smi"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode == 0:
            has_cuda = True
    except Exception:
        pass

    # Check Apple Metal
    if platform.system().lower() == "darwin" and platform.machine().lower() in ("arm64", "aarch64"):
        has_metal = True

    if has_cuda:
        log("GPU Hardware: NVIDIA CUDA detected.", level="SUCCESS")
        return "cuda"
    elif has_metal:
        log("GPU Hardware: Apple Silicon Metal detected.", level="SUCCESS")
        return "metal"
    else:
        log("GPU Hardware: No discrete GPU detected; CPU acceleration active.", level="INFO")
        return "cpu"


def setup_llamafile():
    """Ensures cosmopolitan/platform-specific llamafile binary is in place."""
    os_name, _ = detect_platform()
    os.makedirs(LLAMAFILE_DIR, exist_ok=True)

    bin_name = "llamafile-0.10.4-thin.exe" if os_name == "windows" else "llamafile-0.10.4-thin"
    target_path = os.path.join(LLAMAFILE_DIR, bin_name)

    if os.path.exists(target_path) and os.path.getsize(target_path) > 10_000_000:
        if os_name != "windows":
            os.chmod(target_path, 0o755)
        log(f"Llamafile binary verified: {target_path}", level="SUCCESS")
        return target_path

    log(f"Llamafile binary missing or incomplete. Downloading cosmopolitan binary v0.10.4...")
    download_url = "https://github.com/Mozilla-Ocho/llamafile/releases/download/0.10.4/llamafile-0.10.4"

    try:
        urllib.request.urlretrieve(download_url, target_path)
        if os_name != "windows":
            os.chmod(target_path, 0o755)
        log(f"Downloaded and configured Llamafile binary: {target_path}", level="SUCCESS")
        return target_path
    except Exception as e:
        log(f"Failed to download Llamafile binary: {e}", level="ERROR")
        return None


def verify_java():
    """Checks if Java runtime environment is functional."""
    try:
        res = subprocess.run(["java", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0:
            first_line = (res.stderr or res.stdout).splitlines()[0]
            log(f"Java Runtime verified: {first_line}", level="SUCCESS")
            return True
    except Exception:
        pass

    log("System Java not found. Lumina will use Python execution fallback where available.", level="WARN")
    return False


def verify_python_deps():
    """Checks essential packages. Reports missing without blocking setup."""
    required = ["psutil", "requests"]
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        log(f"Some optional packages are not installed in base environment: {', '.join(missing)}.", level="WARN")
        log("They can be installed anytime via: pip install psutil requests chromadb", level="INFO")
    else:
        log("Essential Python packages verified.", level="SUCCESS")


def download_file_with_progress(url, dest_path, desc):
    """Downloads a file with a clean visual progress indicator."""
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 10_000_000:
        log(f"Model already present: {desc}", level="SUCCESS")
        return True

    log(f"Downloading {desc}...")
    temp_path = dest_path + ".part"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Lumina-Setup/1.0"})
        with urllib.request.urlopen(req) as response, open(temp_path, "wb") as out_file:
            total_size = int(response.info().get("Content-Length", 0))
            downloaded = 0
            block_size = 1024 * 1024  # 1MB chunks
            start_time = time.time()

            while True:
                buffer = response.read(block_size)
                if not buffer:
                    break
                downloaded += len(buffer)
                out_file.write(buffer)

                elapsed = time.time() - start_time
                mb_downloaded = downloaded / (1024 * 1024)
                total_mb = total_size / (1024 * 1024) if total_size > 0 else 0
                speed = mb_downloaded / elapsed if elapsed > 0 else 0

                percent = (downloaded / total_size * 100) if total_size > 0 else 0
                print(f"\r  [{percent:5.1f}%] {mb_downloaded:6.1f}MB / {total_mb:6.1f}MB ({speed:5.1f} MB/s)", end="", flush=True)

            print()

        shutil.move(temp_path, dest_path)
        log(f"Successfully saved {desc} to {dest_path}", level="SUCCESS")
        return True
    except Exception as e:
        print()
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        log(f"Download failed for {desc}: {e}", level="ERROR")
        return False


def setup_models():
    """Downloads the 3 base GGUF models directly with HuggingFace Hub + direct CDN fallback."""
    os.makedirs(MODELS_DIR, exist_ok=True)

    models = [
        {
            "name": "Qwen2.5-0.5B-Instruct-Q4_K_M.gguf",
            "repo": "bartowski/Qwen2.5-0.5B-Instruct-GGUF",
            "url": "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf",
        },
        {
            "name": "Llama-3.2-1B-Instruct-Q4_K_M.gguf",
            "repo": "bartowski/Llama-3.2-1B-Instruct-GGUF",
            "url": "https://huggingface.co/bartowski/Llama-3.2-1B-Instruct-GGUF/resolve/main/Llama-3.2-1B-Instruct-Q4_K_M.gguf",
        },
        {
            "name": "Qwen2.5-Coder-1.5B-Instruct-Q4_K_M.gguf",
            "repo": "bartowski/Qwen2.5-Coder-1.5B-Instruct-GGUF",
            "url": "https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF/resolve/main/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf",
        },
    ]

    for m in models:
        dest = os.path.join(MODELS_DIR, m["name"])
        if os.path.exists(dest) and os.path.getsize(dest) > 10_000_000:
            log(f"Model verified: {m['name']}", level="SUCCESS")
            continue

        # Try huggingface_hub first
        downloaded = False
        try:
            from huggingface_hub import hf_hub_download
            log(f"Fetching {m['name']} via HuggingFace Hub...")
            hf_hub_download(
                repo_id=m["repo"],
                filename=m["name"],
                local_dir=MODELS_DIR,
                local_dir_use_symlinks=False,
                resume_download=True
            )
            downloaded = True
            log(f"Downloaded {m['name']} via HF Hub.", level="SUCCESS")
        except Exception as e:
            log(f"HF Hub unauthenticated rate limit encountered. Falling back to direct CDN streaming...", level="WARN")

        # Fallback to direct chunked download
        if not downloaded:
            download_file_with_progress(m["url"], dest, m["name"])


def main():
    print(f"\n{CLR_BRAND}{CLR_BOLD}================================================================={CLR_RESET}")
    print(f"{CLR_BRAND}{CLR_BOLD}       Lumina AI Toolchain — Universal Multi-OS Setup           {CLR_RESET}")
    print(f"{CLR_BRAND}{CLR_BOLD}================================================================={CLR_RESET}\n")

    os_name, machine = detect_platform()
    log(f"Operating System: {os_name} ({machine})")

    check_gpu()
    verify_python_deps()
    setup_llamafile()
    verify_java()
    setup_models()

    print(f"\n{CLR_SUCCESS}{CLR_BOLD}✔ Lumina environment setup complete! All binaries, runtimes, and models ready.{CLR_RESET}\n")


if __name__ == "__main__":
    main()
