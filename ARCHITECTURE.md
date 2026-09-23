# 📐 Lumina System Architecture & Technical Deep Dive

This document provides a comprehensive technical overview of Lumina's internal architecture, component interactions, subsystems, tools, and testing frameworks.

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
     ┌────────────────────────┬─────────────┼─────────────┬────────────────────────┐
     │                        │             │             │                        │
┌────▼─────────────────┐ ┌────▼────────┐ ┌──▼──────────┐ ┌▼──────────────────┐ ┌───▼──────────────────┐
│ Web Backend & API    │ │ Hardware    │ │ Router &    │ │ Local RAG Engine   │ │ Tool Execution       │
│ (LuminaWebServer)    │ │ Predictor   │ │ Classifier  │ │ (LangChain+Chroma) │ │ Subsystem (Tools/)   │
│                      │ │ (System     │ │ (classifier │ │                    │ │                      │
│                      │ │  Assess)    │ │   .py)      │ │                    │ │                      │
└──────────┬───────────┘ └────┬────────┘ └──┬──────────┘ └┬───────────────────┘ └───┬──────────────────┘
           │                  │             │             │                         │
           └──────────────────┼─────────────┼─────────────┴─────────────────────────┘
                              │             │
                       ┌──────▼─────────────▼──────┐
                       │  SmartSwitch Failover     │
                       │  & Query Buffer Engine    │
                       │     (Smartswitch.py)      │
                       └────────────┬──────────────┘
                                    │
                       ┌────────────▼──────────────┐
                       │  Local Inference Engine   │
                       │    (llamafile / GGUF)     │
                       └───────────────────────────┘
```

---

## 🔬 Core Subsystems

### 1. Dynamic OS Detection & Runtime Resolution (`Lumina.py`)
Rather than relying on globally installed runtimes (`JAVA_HOME`, `PATH`), Lumina inspects the host operating system at startup:
- **OS Identification**: Dynamically detects `macos`, `windows`, and `linux`.
- **Runtime Resolution**: Dynamically maps to the correct bundled JRE (`Jre/Mac-intel/...` or `Jre/Windows/...`) and Python environment (`python-dependencies/macos-intel` or `python-dependencies/windows`).
- **Classpath Assembly**: Assembles a self-contained Java classpath from `./target/classes`, `./lib/*.jar`, and `./target/*.jar` without requiring external build tools at runtime.
- **Process & Output Wrapper**: Intercepts subprocess output in real-time, suppresses runtime noise (SLF4J, JVM reflection warnings), renders ANSI-branded status lines to stdout, and writes 100% of raw timestamped logs to `logs/lumina.log`.

---

### 2. Hardware Sensing & Bandwidth Predictor (`SystemAssess.java`)
Local LLM execution speed on CPU/unified memory is fundamentally memory-bandwidth bound. Lumina uses **OSHI (Operating System and Hardware Information)** to query system hardware directly:

- **Bandwidth Calculation**: Measures true memory throughput ($GB/s$) by executing test prompts against known model byte sizes ($GB$) and tracking prompt token generation speed:
  $$\text{Memory Bandwidth (GB/s)} = \frac{\text{Model Size (GB)} \times \text{Tokens/sec}}{\text{Pass Count}}$$

- **Theoretical Token Prediction (`estimate()`)**: Predicts expected token generation speed based on memory throughput and model quantization:
  $$\text{Tokens/sec} = \frac{\text{Bandwidth (GB/s)}}{\text{Parameters (B)} \times (\text{Quantization Bits} / 8)}$$

- **Fitting Algorithm (`willitfit()`)**: Evaluates model parameter count and quantization bit-width to verify if the uncompressed weights fit within system VRAM or available system RAM.

---

### 3. Portable Inference Engine (`launch_model.py` & `llamafile`)
Lumina uses an embedded **Llamafile** binary (`resources/llamafile/llamafile-0.10.4-thin`) to serve local `.gguf` weights:
- **Background Server Binding**: Dynamically allocates an available local TCP port, spawns a background `llamafile` subprocess via polyglot shell execution, and exposes an OpenAI-compatible HTTP endpoint (`http://127.0.0.1:<port>/v1/chat/completions` and `/v1/completions`).
- **Process Isolation & Lifecycle**: Managed with graceful SIGTERM/SIGKILL handlers, port release monitors, and automated health checks.

---

### 4. SmartSwitch Dynamic Failover & Query Preservation (`scripts/Smartswitch.py`)
Provides autonomous health monitoring, performance degradation detection, and zero-loss hot-swapping:
- **Memory Tracking (`raminitilization`)**: Baselines and continuously tracks RSS RAM or VRAM footprint.
- **Degradation Detection**: Identifies token generation throughput drops ($\text{current T/s} < 0.75 \times \text{baseline T/s}$) or memory inflation beyond threshold.
- **Hot-Swap Failover**: Terminates the degraded primary model and automatically launches a lightweight fallback model (e.g. `Qwen2.5-0.5B`) on the **exact same port**.
- **Query Buffer Subsystem (`query_buffer.json`)**: Buffers active in-flight requests before generation; if an active generation is interrupted during a hot-swap, the preserved query is automatically replayed to the fallback model once live.

---

### 5. Intelligent Router & Intent Classifier (`scripts/classifier.py`)
Routes queries dynamically to optimize response latency and resource allocation:
- **Casual vs. Technical Routing (`classify`)**: Evaluates incoming queries using lightweight zero-temperature classification (casual greetings $\rightarrow$ quick response; technical/domain tasks $\rightarrow$ full RAG / tool pipeline).
- **Context Intent Detection (`needs_context`)**: Uses heuristic cues and LLM intent evaluation to determine if a query requires conversational history.
- **Context Vector Storage**: Persists conversation history in `data/context_chroma_db` using LangChain embeddings and enables similarity retrieval (`searchforuserscontext`).

---

### 6. Local RAG & Agentic Reasoning Pipeline (`scripts/rag.py` & `scripts/agentic_rag.py`)
Provides offline document retrieval and multi-step reasoning:
- **Text Chunking**: Uses `RecursiveCharacterTextSplitter` (chunk size: 800, overlap: 80).
- **Vector Storage**: Embeds chunks using HuggingFace BGE transformers and stores vectors in a local `chroma_db/` instance.
- **Agentic Loop**: Executes iterative retrieval-augmented prompt engineering with structured logging written to `logs/Agentic.log`.

---

### 7. Modular Tool Execution Subsystem (`Tools/` & `scripts/test_executor.py`)
Lumina provides a suite of modular Python tools that can be executed independently or invoked by the agentic pipeline via `test_executor.py`:

| Tool Script | File Path | Functionality |
| :--- | :--- | :--- |
| **`code_and_run.py`** | `Tools/code_and_run.py` | Executes Python code dynamically in isolated subprocesses and captures stdout/stderr. |
| **`color_print.py`** | `Tools/color_print.py` | Terminal ANSI and color formatting utility for CLI reporting. |
| **`delete_file.py`** | `Tools/delete_file.py` | Safe file removal with validation and error reporting. |
| **`make_thumbnail.py`** | `Tools/make_thumbnail.py` | Generates resized image thumbnails for documents and UI previews. |
| **`peek_code.py`** | `Tools/peek_code.py` | Selective line inspection and code snippet extraction. |
| **`pip_install.py`** | `Tools/pip_install.py` | Installs Python packages into Lumina's bundled runtime directory. |
| **`read_file.py`** | `Tools/read_file.py` | Safe file reader with encoding fallbacks and size limits. |
| **`save_file.py`** | `Tools/save_file.py` | Atomic file writer for persistence across scripts and tools. |
| **`wiki_scrape.py`** | `Tools/wiki_scrape.py` | Fetches and cleans Wikipedia articles for automated knowledge ingestion. |
| **`test_executor.py`** | `scripts/test_executor.py` | Parses LLM tool syntax (e.g. `save_file("path", "data")`) and dispatches commands to the `Tools/` directory. |

---

### 8. Automated Test & Benchmark Suite (`tests/`)
Lumina includes a comprehensive `pytest` test suite configured via `pytest.ini` and `tests/conftest.py`:

| Test Suite | Purpose |
| :--- | :--- |
| **`test_assesser_vs_router_benchmark.py`** | Validates `SystemAssess` theoretical T/s predictions against actual `llamafile` inference speeds across all 4 bundled models (`Phi-3.5-mini 3.8B`, `Llama-3.2 1B`, `Qwen-Coder 1.5B`, `Qwen 0.5B`) with automated deletion of `bandwidth.txt` per run. Automatically exports results to `logs/benchmark_results.json`. |
| **`test_router_classification.py`** | Verifies casual vs. technical routing accuracy (100%), context intent triggers, and Chroma vector database memory storage and retrieval. |
| **`test_smartswitch_stress.py`** | Stresses the 3.8B model with heavy context and KV-cache pressure, measures throughput drops (e.g. $11.24 \rightarrow 7.93\text{ T/s}$), triggers hot-swap failover, benchmarks millisecond switchover latency, and tests query preservation. |

---

## 🔄 Customization & Extensibility

For instructions on swapping models, vector databases, inference backends, or runtimes, please refer to **[`SWAPPABLE.md`](file:///Users/apple/Lumina/SWAPPABLE.md)**.
