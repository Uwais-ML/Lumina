# 📐 Lumina System Architecture & Technical Deep Dive

This document provides a comprehensive technical overview of Lumina's internal architecture, component interactions, and algorithms.

---

## 🏗️ High-Level System Architecture

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

## 🔬 Core Subsystems

### 1. Dynamic OS Detection & Runtime Resolution (`Lumina.py`)
Rather than relying on globally installed runtimes (`JAVA_HOME`, `PATH`), Lumina inspects the host operating system at startup:
- **OS Identification**: Detects `macos`, `windows`, and `linux`.
- **Runtime Resolution**: Dynamically maps to the correct bundled JRE (`Jre/Mac-intel/...` or `Jre/Windows/...`) and Python environment (`python-dependencies/...`).
- **Classpath Assembly**: Assembles a self-contained Java classpath from `./target/classes` and `./lib/*.jar` without requiring Maven at runtime.
- **Process & Output Wrapper**: Intercepts subprocess output in real-time, suppresses runtime noise (SLF4J, JVM reflection warnings), renders ANSI-branded status lines to stdout, and writes 100% of raw timestamped logs to `logs/lumina.log`.

---

### 2. Hardware Sensing & Bandwidth Predictor (`SystemAssess.java`)
Local LLM execution speed on CPU/unified memory is fundamentally memory-bandwidth bound. Lumina uses **OSHI (Operating System and Hardware Information)** to query system hardware directly:

- **Bandwidth Calculation**: Measures true memory throughput ($GB/s$) by executing test prompts against known model byte sizes ($GB$) and tracking prompt token generation speed:
  $$\text{Memory Bandwidth (GB/s)} = \frac{\text{Model Size (GB)} \times \text{Tokens/sec}}{\text{Pass Count}}$$

- **Fitting Algorithm (`willitfit()`)**: Evaluates model parameter count and quantization bit-width to verify if the uncompressed weights fit within system VRAM/RAM:
  $$\text{Model Size (GB)} = \text{Parameters (B)} \times \left(\frac{\text{Quantization Bits}}{8}\right)$$

---

### 3. Portable Inference Engine (`Runit.java` & `llamafile`)
Lumina uses an embedded **Llamafile** binary (`resources/llamafile/llamafile-0.10.4-thin`) to serve local `.gguf` weights:
- **Background Server Binding**: Dynamically searches for an available local TCP port, spawns a background `llamafile` subprocess, and exposes an OpenAI-compatible HTTP endpoint (`http://127.0.0.1:<port>/v1/completions`).
- **Process Isolation & Lifecycle**: Managed via Java `ProcessBuilder` with shutdown hooks ensuring zero orphaned processes upon termination.

---

### 4. Multi-Threaded Web Server (`LuminaWebServer.java`)
Built on Java's lightweight `com.sun.net.httpserver.HttpServer`:
- **`GET /api/models`**: Reads model catalog from `resources/llmstore.json`, runs hardware fit analysis, and returns computed token speed predictions.
- **`GET /api/system`**: Returns host OS, CPU architecture, and measured bandwidth.
- **`POST /api/complete`**: Receives prompt completions from the IDE Web UI and proxies them to the active local Llamafile instance.
- **`POST /api/install`**: Executes background HuggingFace model downloads with live SSE log streaming (`GET /api/status`).

---

### 5. Local RAG & Agentic RAG Pipeline (`scripts/rag.py` & `scripts/agentic_rag.py`)
Provides offline document retrieval and multi-step reasoning:
- **Text Chunking**: Uses `RecursiveCharacterTextSplitter` (chunk size: 800, overlap: 80).
- **Vector Storage**: Embeds chunks using HuggingFace BGE transformers and stores vectors in a local `chroma_db/` instance.
- **Agentic Loop**: Executes iterative retrieval-augmented prompt engineering with structured logging written to `logs/Agentic.log`.

---

## 🔄 Customization & Extensibility

For instructions on swapping models, vector databases, inference backends, or runtimes, please refer to **[`SWAPPABLE.md`](file:///Users/apple/Lumina/SWAPPABLE.md)**.
