# ⚡ Lumina AI Engine

**Lumina** is a self-contained, cross-platform local LLM infrastructure, hardware performance predictor, and Agentic RAG engine. It delivers zero-dependency, local-first AI execution with an integrated Web Store dashboard, real-time code completion server, and hardware bandwidth predictor.

Lumina is **100% self-sustained** — shipping with pre-bundled JREs, embedded Python environments, pre-packaged Java libraries (`./lib/`), and an OS-agnostic dynamic dispatcher.

---

## ⚡ Coming Soon: Lumina SmartSwitch™

> [!IMPORTANT]
> **SmartSwitch™ (In Active Development)**
> An intelligent model routing engine that dynamically evaluates prompt complexity, real-time hardware memory pressure (VRAM/RAM), and target latency requirements. SmartSwitch automatically routes requests on-the-fly between sub-second lightweight models (e.g., Qwen 0.5B) and heavy reasoning models (e.g., Llama 3B / DeepSeek) with zero manual intervention.

---

## 📐 System Architecture

```
                               ┌─────────────────────────┐
                               │     User Interface      │
                               │  (CLI / Web Store UI)   │
                               └────────────┬────────────┘
                                            │
                               ┌────────────▼────────────┐
                               │   Lumina CLI Engine     │
                               │      (Lumina.py)        │
                               └────────────┬────────────┘
                                            │
               ┌────────────────────────────┼────────────────────────────┐
               │                            │                            │
   ┌───────────▼───────────┐    ┌───────────▼───────────┐    ┌───────────▼───────────┐
   │ Lumina Web Backend    │    │ Hardware Predictor    │    │ Local RAG Engine      │
   │ (LuminaWebServer)     │    │ (SystemAssess + OSHI) │    │ (LangChain + Chroma)  │
   └───────────┬───────────┘    └───────────┬───────────┘    └───────────┬───────────┘
               │                            │                            │
               └────────────────────────────┼────────────────────────────┘
                                            │
                               ┌────────────▼────────────┐
                               │ Local Inference Engine  │
                               │  (llamafile / GGUF)     │
                               └─────────────────────────┘
```

---

## 🔬 How Lumina Works: Technical Deep Dive

### 1. Dynamic OS Detection & Runtime Resolution (`Lumina.py`)
Rather than relying on global system environment variables (`JAVA_HOME`, `PATH`), `Lumina.py` inspects the host operating system at startup:
- **OS Identification**: Distinguishes between `macos`, `windows`, and `linux`.
- **Runtime Resolution**: Dynamically maps to the correct bundled JRE (`Jre/Mac-intel/...` or `Jre/Windows/...`) and Python environment (`python-dependencies/...`).
- **Classpath Assembly**: Assembles a self-contained Java classpath from `./target/classes` and `./lib/*.jar` without requiring Maven at runtime.

### 2. Hardware Sensing & Bandwidth Predictor (`SystemAssess.java`)
Local LLM execution speed on CPU/unified memory is fundamentally memory-bandwidth bound. Lumina uses **OSHI (Operating System and Hardware Information)** to query system hardware directly:
- **Bandwidth Calculation**: Measures true memory throughput ($GB/s$) by executing test prompts against known model byte sizes ($GB$) and tracking prompt token generation speed:
  $$\text{Memory Bandwidth (GB/s)} = \frac{\text{Model Size (GB)} \times \text{Tokens/sec}}{\text{Pass Count}}$$
- **Fitting Algorithm (`willitfit()`)**: Evaluates model parameter count and quantization bit-width to verify if the uncompressed weights fit within system VRAM/RAM:
  $$\text{Model Size (GB)} = \text{Parameters (B)} \times \left(\frac{\text{Quantization Bits}}{8}\right)$$

### 3. Portable Inference Engine (`Runit.java` & `llamafile`)
Lumina uses an embedded **Llamafile** binary (`resources/llamafile/llamafile-0.10.4-thin`) to serve local `.gguf` weights:
- **Background Server Binding**: Searches for an available local TCP port, spawns a background `llamafile` subprocess, and exposes an OpenAI-compatible HTTP endpoint (`http://127.0.0.1:<port>/v1/completions`).
- **Process Isolation & Lifecycle**: Managed via Java `ProcessBuilder` with shutdown hooks ensuring zero orphaned processes upon termination.

### 4. Multi-Threaded Web Server (`LuminaWebServer.java`)
Built on Java's `com.sun.net.httpserver.HttpServer`:
- **`GET /api/models`**: Reads model catalog from `resources/llmstore.json`, runs hardware fit analysis, and returns computed token speed predictions.
- **`GET /api/system`**: Returns host OS, CPU architecture, and measured bandwidth.
- **`POST /api/complete`**: Receives prompt completions from the IDE Web UI and proxies them to the active local Llamafile instance.
- **`POST /api/install`**: Executes background HuggingFace model downloads with live SSE log streaming (`GET /api/status`).

### 5. Local RAG & Agentic RAG Engine (`scripts/rag.py` & `scripts/agentic_rag.py`)
Provides offline document retrieval and multi-step reasoning:
- **Text Chunking**: Uses `RecursiveCharacterTextSplitter` (chunk size: 800, overlap: 80).
- **Vector Storage**: Embeds chunks using HuggingFace BGE transformers and stores vectors in a local `chroma_db/` instance.
- **Agentic Loop**: Executes iterative retrieval-augmented prompt engineering with structured logging written to `logs/Agentic.log`.

---

## 🚀 Quick Start Guide

Use the top-level wrapper (`./lumina` on macOS/Linux or `lumina.bat` on Windows):

```bash
# Display CLI menu and auto-detected system runtimes
./lumina

# 1. Launch the Lumina Web Server & Model Store Dashboard
./lumina --models

# 2. Run hardware benchmark across local GGUF models
./lumina --bench

# 3. Estimate hardware bandwidth and predicted token speed
./lumina --assess

# 4. Run local RAG vector store pipeline
./lumina --rag

# 5. Run multi-step Agentic RAG reasoning engine
./lumina --agentic

# 6. Launch a specific GGUF model via llamafile server
./lumina --launch Llama-3.2-1B-Instruct-Q4_K_M

# 7. Download base test models
./lumina --setup
```

---

## 📁 Repository Structure

```
Lumina/
├── Lumina.py                          # Dynamic OS detector & CLI dispatcher
├── lumina                             # Executable CLI script (macOS/Linux)
├── lumina.bat                         # Executable Batch script (Windows)
├── SWAPPABLE.md                       # Modular component swapping guide
├── pom.xml                            # Maven build configuration
├── README.md / LICENSE
│
├── src/
│   ├── java/lumina/                   # Lumina Java source (package `lumina`)
│   │   ├── LuminaWebServer.java       # Local HTTP server & REST API
│   │   ├── SystemAssess.java          # OSHI hardware sensor & bandwidth predictor
│   │   ├── Runit.java                 # Llamafile benchmark engine
│   │   ├── LLM.java                   # Model metadata & store parser
│   │   └── downloadmodel.java         # HuggingFace model downloader bridge
│   ├── main/resources/web/            # Frontend Web UI (index.html, ide.html)
│   └── test/java/lumina/              # Unit test suites
│
├── scripts/                           # Python RAG & Agentic scripts
│   ├── rag.py                         # Text chunking, embedding & Chroma RAG
│   ├── agentic_rag.py                 # Multi-step Agentic RAG reasoning engine
│   ├── launch_model.py                # Llamafile model server launcher
│   ├── download_base_models.py        # Base models downloader
│   └── download_model.py              # HuggingFace hub model downloader
│
├── models/                            # Local GGUF model files (.gguf)
├── resources/                         # Shared project assets
│   ├── bandwidth.txt                  # Measured system memory bandwidth
│   ├── llmstore.json                  # Model catalog & quantization specs
│   ├── web/                           # Web assets (index.html, ide.html)
│   └── llamafile/                     # Portable Llamafile executable
│
├── lib/                               # Bundled Java dependencies (OSHI, Jackson, JNA, Requests)
├── logs/                              # Execution & Agentic RAG log directory
├── chroma_db/                         # Local Chroma vector database
├── Jre/                               # Bundled JRE runtimes (Mac-intel, Windows)
└── python-dependencies/               # Bundled Python runtimes (Mac-intel, Windows)
```

---

## 🔄 Swappable Architecture

Lumina is designed to be fully modular. See **[`SWAPPABLE.md`](file:///Users/apple/Lumina/SWAPPABLE.md)** for step-by-step instructions on how to swap:
- **GGUF Models**: Drop new models directly into `models/`.
- **Inference Engines**: Replace Llamafile with Ollama, vLLM, or `llama-server`.
- **Vector DB & Embeddings**: Swap Chroma for FAISS, Qdrant, or custom embeddings.
- **Runtimes**: Swap bundled JRE or CPython versions.
- **Frontend UI**: Edit HTML/CSS/JS in `resources/web/`.

---

## 📄 License

Distributed under the Apache 2.0 License. See `LICENSE` for details.
