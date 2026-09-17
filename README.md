# ⚡ Lumina AI Engine

> **A self-contained, cross-platform local AI toolchain and inference framework.**  
> Plug & play out of the box on macOS, Windows, and Linux — zero external dependencies, zero environment configuration.

---

## ✨ Features

- 🔌 **Plug & Play Runtime** — Bundles its own isolated JRE and CPython environments. No need to install Java, Python, or build tools globally.
- ⚡ **Hardware Performance Predictor** — Senses memory bandwidth using OSHI and predicts exact tokens/sec generation speed before running models.
- 🏪 **Interactive Web Dashboard & Store** — Explore, monitor, download, and test local GGUF models through a browser-based UI (`http://localhost:8080`).
- 🤖 **Offline RAG & Agentic Reasoning** — Local document ingestion, semantic chunking, Chroma vector storage, and multi-step reasoning.
- 🚀 **High-Performance Inference** — Runs quantized `.gguf` weights locally via an embedded, multi-platform Llamafile server with an OpenAI-compatible API.
- 🎨 **Enterprise CLI UI & Smart Logging** — Noise-filtered, ANSI-branded terminal interface with full timestamped audit logs recorded to `logs/lumina.log`.

---

## 🚀 Quick Start

Clone the repository and run the Lumina CLI wrapper:

### macOS / Linux
```bash
# Make sure wrapper is executable (first time only)
chmod +x lumina

# Open the interactive Lumina CLI
./lumina
```

### Windows (PowerShell / Command Prompt)
```cmd
# Open the interactive Lumina CLI
.\lumina.bat
```

---

## 📖 Command Reference

Lumina provides a unified CLI dispatcher for all operations.

| Command | Purpose | Example |
| :--- | :--- | :--- |
| `--models` | Launches the local Web Dashboard & Model Store | `./lumina --models` |
| `--assess` | Senses hardware & predicts tokens/sec for target models | `./lumina --assess` |
| `--bench` | Runs local hardware benchmark across GGUF models | `./lumina --bench` |
| `--setup` | Downloads default base GGUF models | `./lumina --setup` |
| `--launch` | Spawns a background GGUF model server with OpenAI API | `./lumina --launch Llama-3.2-1B-Instruct-Q4_K_M` |
| `--rag` | Ingests documents and runs local vector search (Chroma) | `./lumina --rag` |
| `--agentic` | Executes multi-step Agentic RAG reasoning loop | `./lumina --agentic` |
| `--download` | Downloads a model directly from HuggingFace | `./lumina --download` |
| `--install` | Installs Python packages into the bundled runtime | `./lumina --install scikit-learn` |
| `--dependencies` | Validates & installs all required Python dependencies | `./lumina --dependencies` |

---

## 💻 Common Workflows

### 1. Launching the Web Store & Model Manager
Launch the local web server and open your browser:
```bash
./lumina --models
```
👉 Open **`http://localhost:8080`** to view available models, inspect RAM requirements, and test code completions in the built-in IDE.

---

### 2. Assessing Your Hardware
Before downloading large models, check your system's memory bandwidth and predicted tokens/sec:
```bash
./lumina --assess
```
```text
[Lumina Java] Detected OS: macos | JRE: .../jdk-25.0.4+7-jre/...
[Lumina Assess] 📊 Calculated True Bandwidth: 28.54 GB/s
[Lumina Assess] ⚡ Estimated tokens/sec for 1.5B Q4: 25.85 tok/s
[Lumina SystemAssess] ✔ SystemAssess completed successfully.
```

---

### 3. Launching a Local Model Server
Start an OpenAI-compatible local model server in the background:
```bash
./lumina --launch Llama-3.2-1B-Instruct-Q4_K_M
```
* **API Endpoint**: `http://127.0.0.1:<port>/v1/chat/completions`
* **Log Location**: `logs/llamafile_<model>.log`

---

### 4. Running Offline Document RAG
Query your local knowledge base without sending data to the cloud:
```bash
./lumina --rag
```

---

## 📁 Project Structure

```text
Lumina/
├── Lumina.py               # Unified cross-platform CLI dispatcher
├── lumina                  # CLI launcher for macOS / Linux
├── lumina.bat              # CLI launcher for Windows
├── models/                 # Local GGUF models directory (.gguf)
├── scripts/                # Python inference, RAG, and launcher scripts
│   ├── rag.py              # Document ingestion & Chroma vector search
│   ├── agentic_rag.py      # Multi-step Agentic reasoning pipeline
│   ├── launch_model.py     # Local GGUF model server launcher
│   └── download_base_models.py
├── src/java/lumina/        # Core Java backend & Web Server
│   ├── LuminaWebServer.java# HTTP server & API endpoints
│   ├── SystemAssess.java   # Hardware bandwidth sensor & predictor
│   └── Runit.java          # Benchmark runner
├── resources/              # Web UI templates & llamafile binaries
│   ├── web/                # Web Dashboard (index.html, ide.html)
│   └── llamafile/          # Multi-platform llamafile binary
├── logs/                   # Raw timestamped execution logs (lumina.log)
├── Jre/                    # Bundled JRE runtimes (macOS, Windows)
└── python-dependencies/    # Bundled CPython runtimes (macOS, Windows)
```

---

## 🔍 Diagnostics & Logs

Lumina keeps your terminal output clean and noise-free while recording 100% of raw subprocess output, timestamps, and error stacks to:
```text
logs/lumina.log
```
If you ever encounter an issue, inspect `logs/lumina.log` for complete diagnostic traces.

---

## 📚 Advanced Documentation

- 🔄 **[SWAPPABLE.md](file:///Users/apple/Lumina/SWAPPABLE.md)** — Guide to swapping GGUF models, inference backends (Ollama/vLLM), vector stores (FAISS/Chroma), and runtimes.
- 📐 **[ARCHITECTURE.md](file:///Users/apple/Lumina/ARCHITECTURE.md)** — Deep dive into system architecture, hardware sensing formulas, and runtime resolution.

---

## 📄 License

Distributed under the Apache 2.0 License. See `LICENSE` for details.
