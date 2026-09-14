# 🔄 Lumina Swappable Components Guide (`SWAPPABLE.md`)

This guide explains how to swap, customize, or replace any part of Lumina — including GGUF models, the local inference engine (Llamafile / Ollama / llama.cpp), vector stores, embedded runtimes, frontend templates, and backend logic.

---

## 📋 Table of Contents

1. [Swapping GGUF Models](#1-swapping-gguf-models)
2. [Swapping the Inference Engine (Llamafile / llama.cpp / Ollama)](#2-swapping-the-inference-engine)
3. [Swapping Vector DB & Embeddings (RAG / Agentic RAG)](#3-swapping-vector-db--embeddings)
4. [Swapping Runtimes (JRE & Python Dependencies)](#4-swapping-runtimes)
5. [Swapping Web UI & IDE Templates](#5-swapping-web-ui--ide-templates)
6. [Swapping Backend API Handlers](#6-swapping-backend-api-handlers)

---

## 1. Swapping GGUF Models

Lumina supports any `.gguf` model architecture supported by Llamafile / `llama.cpp` (Llama 3, Qwen 2.5, Phi 3.5, Mistral, DeepSeek, etc.).

### Step 1: Add your GGUF model file
Download or copy your `.gguf` file directly into the `models/` directory:
```
models/MyCustomModel-7B-Q4_K_M.gguf
```

### Step 2: Register in `resources/llmstore.json` (Optional)
To display your custom model in the Web Store UI (`./lumina --models`), append an entry to `resources/llmstore.json`:

```json
{
  "id": 10,
  "name": "My Custom Model 7B",
  "filename_pattern": "MyCustomModel-7B-Q4_K_M.gguf",
  "link": "https://huggingface.co/your-repo/MyCustomModel-7B-Q4_K_M.gguf",
  "quantization": "Q4_K_M",
  "parameters": "7B",
  "pros": "High performance local model",
  "cons": "Requires 6GB RAM"
}
```

### Step 3: Launch or Benchmark
- Launch via CLI:
  ```bash
  ./lumina --launch MyCustomModel-7B-Q4_K_M
  ```
- To include it in the hardware benchmark, update `modelPath` array in `src/java/lumina/Runit.java`:
  ```java
  modelPath[0] = "models/MyCustomModel-7B-Q4_K_M.gguf";
  ```

---

## 2. Swapping the Inference Engine

By default, Lumina uses `llamafile-0.10.4-thin` located in `resources/llamafile/`. You can swap it for a newer llamafile, a `llama-server` binary, or an external API like Ollama or vLLM.

### Option A: Swap the binary file
1. Download your new inference binary (e.g. `llamafile-v0.11` or `llama-server`).
2. Paste it into `resources/llamafile/your_new_binary`.
3. Update the executable name in these 2 files:
   - **`src/java/lumina/Runit.java`** (line ~58):
     ```java
     String baseName = "your_new_binary";
     ```
   - **`scripts/launch_model.py`** (line ~25):
     ```python
     llamaname = "your_new_binary"
     ```

### Option B: Swap to an external engine (Ollama / vLLM / LocalAI)
To route completions to Ollama or another local HTTP server instead of launching llamafile:
- Edit **`src/java/lumina/LuminaWebServer.java`** in `CompleteHandler`:
  ```java
  // Change target endpoint URI:
  HttpRequest request = HttpRequest.newBuilder()
          .uri(URI.create("http://localhost:11434/api/generate")) // e.g. Ollama endpoint
          .header("Content-Type", "application/json")
          ...
  ```

---

## 3. Swapping Vector DB & Embeddings (RAG / Agentic RAG)

The RAG pipelines (`scripts/rag.py` and `scripts/agentic_rag.py`) use **LangChain + Chroma + HuggingFace Embeddings**.

### Swap Embedding Model
In `scripts/rag.py` or `scripts/agentic_rag.py`:
```python
# Default: HuggingFace BGE / MiniLM
embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-small-en-v1.5")

# SWAP TO: Ollama / SentenceTransformers / Custom local model:
# embeddings = HuggingFaceEmbeddings(model_name="all-mpnet-base-v2")
```

### Swap Vector Database (Chroma -> FAISS / Qdrant)
In `scripts/rag.py` or `scripts/agentic_rag.py`:
```python
# SWAP FROM Chroma:
# vectorstore = Chroma(persist_directory="./chroma_db", embedding_function=embeddings)

# TO FAISS:
from langchain_community.vectorstores import FAISS
vectorstore = FAISS.from_documents(docs, embeddings)
```

---

## 4. Swapping Runtimes (JRE & Python Dependencies)

Lumina auto-detects system OS and selects the bundled runtimes. You can swap or update the bundled JDK / CPython runtimes for ARM64, Linux, or custom versions.

### Swap Java JRE
1. Paste your JRE folder into `Jre/` (e.g. `Jre/Linux/` or `Jre/Mac-arm64/`).
2. Update the folder detection in `Lumina.py` (`get_bundled_jre()`):
   ```python
   target_dir = os.path.join(PROJECT_ROOT, "Jre", "YourCustomFolder")
   ```

### Swap Python Environment
1. Paste your virtualenv / embedded Python into `python-dependencies/`.
2. Update path in `Lumina.py` (`get_bundled_python()`):
   ```python
   home_dir = os.path.join(PROJECT_ROOT, "python-dependencies", "YourCustomPython")
   ```

---

## 5. Swapping Web UI & IDE Templates

All Web UI HTML/CSS/JavaScript files live in `resources/web/`.

- **Web Dashboard**: `resources/web/index.html` (customize model store layout, CSS theme, cards).
- **Code Autocomplete IDE**: `resources/web/ide.html` (customize IDE keybindings, editor area, theme).

Because `LuminaWebServer.java` loads assets dynamically via `resources/web/`, edits to HTML/CSS take effect immediately without recompiling Java!

---

## 6. Swapping Backend API Handlers

To add a new API route or change business logic in the Java backend:

1. Open `src/java/lumina/LuminaWebServer.java`.
2. Register a new handler in `main()`:
   ```java
   server.createContext("/api/mycustomroute", new MyCustomHandler());
   ```
3. Implement `HttpHandler`:
   ```java
   static class MyCustomHandler implements HttpHandler {
       @Override
       public void handle(HttpExchange exchange) throws IOException {
           sendJsonResponse(exchange, 200, "{\"status\": \"ok\"}");
       }
   }
   ```
4. Recompile with `./lumina --models` (auto-compiles changes).
