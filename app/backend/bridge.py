"""
app/backend/bridge.py - Real-time Stdio IPC Bridge for Electron.

Enables direct, zero-socket, line-delimited JSON event streaming between
Electron's Main Process and the Python backend engine.

Protocol:
Electron -> stdin:
  {"id": "req_1", "action": "chat_stream", "conversation_id": "...", "messages": [...], "mode": "chat", "model": "qwen"}
  {"id": "req_2", "action": "list_models"}
  {"id": "req_3", "action": "get_status"}
  {"id": "req_4", "action": "list_conversations"}
  {"id": "req_5", "action": "get_conversation", "conversation_id": "..."}
  {"id": "req_6", "action": "delete_conversation", "conversation_id": "..."}
  {"id": "req_7", "action": "launch_model", "model": "..."}
  {"id": "req_8", "action": "rag_ingest", "text": "...", "filename": "..."}

Python -> stdout:
  {"req_id": "req_1", "type": "message:start", ...}
  {"req_id": "req_1", "type": "message:status", ...}
  {"req_id": "req_1", "type": "message:delta", "delta": "..."}
  {"req_id": "req_1", "type": "message:complete", ...}
  {"req_id": "req_2", "type": "response", "data": {...}}
"""

import os
import sys
import json
import time
import asyncio
import logging
from datetime import datetime

# ── Stdout guard: keep stdout 100% pure JSON for Electron ───────────────────
# Save real stdout before anything else. All prints/logs go to stderr only.
_REAL_STDOUT = sys.__stdout__
sys.stdout = sys.stderr  # redirect accidental prints to stderr

# Setup paths
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(BACKEND_DIR)
PROJECT_ROOT = os.path.dirname(APP_DIR)

def _ensure_pythonpath():
    system = sys.platform.lower()
    if "darwin" in system:
        sp = os.path.join(PROJECT_ROOT, "python-dependencies", "macos-intel", "lib", "python3.12", "site-packages")
    elif "win" in system:
        sp = os.path.join(PROJECT_ROOT, "python-dependencies", "windows", "Lib", "site-packages")
    else:
        sp = os.path.join(PROJECT_ROOT, "python-dependencies", "linux-intel", "lib", "python3.12", "site-packages")
    
    scripts_dir = os.path.join(PROJECT_ROOT, "scripts")
    tools_dir = os.path.join(PROJECT_ROOT, "Tools")

    for path in [sp, scripts_dir, tools_dir, PROJECT_ROOT]:
        if os.path.exists(path) and path not in sys.path:
            sys.path.insert(0, path)

_ensure_pythonpath()

from streaming_service import LuminaStreamEngine, ConversationStore

# Configure logging to file only so stdout remains 100% clean JSON
log_file = os.path.join(PROJECT_ROOT, "logs", "bridge.log")
os.makedirs(os.path.dirname(log_file), exist_ok=True)
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] LuminaBridge: %(message)s"
)
logger = logging.getLogger("LuminaBridge")

engine = LuminaStreamEngine()


def emit(data: dict):
    """Outputs single JSON line to real stdout (Electron IPC channel)."""
    _REAL_STDOUT.write(json.dumps(data, ensure_ascii=False) + "\n")
    _REAL_STDOUT.flush()


async def handle_chat_stream(req_id: str, payload: dict):
    """Handles real-time streaming request and emits line-delimited events."""
    conversation_id = payload.get("conversation_id")
    messages = payload.get("messages", [])
    mode = payload.get("mode", "chat")
    model = payload.get("model", "qwen")
    temperature = float(payload.get("temperature", 0.7))
    max_tokens = int(payload.get("max_tokens", 2048))

    full_text = ""
    complete_event = None

    try:
        async for event in engine.stream_chat(
            messages=messages,
            mode=mode,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            conversation_id=conversation_id
        ):
            event["req_id"] = req_id
            emit(event)

            if event.get("type") == "message:delta":
                full_text += event.get("delta", "")
            elif event.get("type") == "message:complete":
                complete_event = event

        # Auto-persist conversation if conversation_id was supplied
        if conversation_id and full_text:
            conv = ConversationStore.get(conversation_id)
            if not conv:
                user_msg = next((m["content"] for m in messages if m.get("role") == "user"), "New Chat")
                title = user_msg[:36] + ("..." if len(user_msg) > 36 else "")
                conv = {
                    "id": conversation_id,
                    "title": title,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                    "messages": messages,
                    "mode": mode,
                    "model": model
                }
            
            assistant_msg = {
                "id": complete_event.get("id") if complete_event else f"msg_{int(time.time())}",
                "role": "assistant",
                "content": full_text,
                "sources": complete_event.get("sources", []) if complete_event else [],
                "tools": complete_event.get("tools", []) if complete_event else [],
                "timestamp": datetime.now().isoformat()
            }
            conv_messages = [m for m in messages if m.get("role") != "assistant"]
            conv_messages.append(assistant_msg)
            conv["messages"] = conv_messages
            conv["updated_at"] = datetime.now().isoformat()
            ConversationStore.save(conv)

    except Exception as e:
        logger.exception(f"Bridge chat stream error for req {req_id}")
        emit({
            "req_id": req_id,
            "type": "message:error",
            "error": str(e)
        })


async def process_command(line: str):
    """Parses and executes a command from Electron."""
    line = line.strip()
    if not line:
        return

    try:
        req = json.loads(line)
    except Exception as e:
        logger.error(f"Malformed JSON: {line} - {e}")
        return

    req_id = req.get("id", f"req_{int(time.time()*1000)}")
    action = req.get("action")

    if action == "chat_stream":
        asyncio.create_task(handle_chat_stream(req_id, req))

    elif action == "ping":
        engine.refresh_port()
        emit({"req_id": req_id, "type": "response", "data": {"status": "pong", "port": engine.port}})

    elif action == "list_conversations":
        convs = ConversationStore.load_all()
        summaries = [{
            "id": c.get("id"),
            "title": c.get("title", "Untitled Chat"),
            "created_at": c.get("created_at"),
            "updated_at": c.get("updated_at"),
            "message_count": len(c.get("messages", [])),
            "mode": c.get("mode", "chat")
        } for c in convs]
        emit({"req_id": req_id, "type": "response", "data": summaries})

    elif action == "get_conversation":
        conv_id = req.get("conversation_id")
        conv = ConversationStore.get(conv_id)
        emit({"req_id": req_id, "type": "response", "data": conv})

    elif action == "delete_conversation":
        conv_id = req.get("conversation_id")
        success = ConversationStore.delete(conv_id)
        emit({"req_id": req_id, "type": "response", "data": {"status": "deleted" if success else "not_found"}})

    elif action == "list_models":
        models_dir = os.path.join(PROJECT_ROOT, "models")
        local_models = []
        if os.path.isdir(models_dir):
            for f in os.listdir(models_dir):
                if f.endswith(".gguf"):
                    p = os.path.join(models_dir, f)
                    local_models.append({
                        "name": f[:-5],
                        "filename": f,
                        "size_mb": round(os.path.getsize(p)/(1024*1024), 1),
                        "path": p
                    })
        store_file = os.path.join(PROJECT_ROOT, "resources", "llmstore.json")
        catalog = []
        if os.path.exists(store_file):
            try:
                with open(store_file, "r", encoding="utf-8") as sf:
                    catalog = json.load(sf)
            except Exception:
                pass
        emit({"req_id": req_id, "type": "response", "data": {"local": local_models, "catalog": catalog}})

    elif action == "get_status":
        engine.refresh_port()
        status_file = os.path.join(PROJECT_ROOT, "data", "status.txt")
        raw_status = {}
        if os.path.exists(status_file):
            try:
                with open(status_file, "r", encoding="utf-8") as sf:
                    raw_status = json.load(sf)
            except Exception:
                raw_status = {}

        import psutil
        active_model_info = {}
        # Find first currently running model
        if isinstance(raw_status, dict):
            for m_name, info in reversed(list(raw_status.items())):
                if isinstance(info, dict):
                    pid = info.get("PID")
                    if pid and psutil.pid_exists(pid):
                        # Extract latest real T/s from log file if present
                        log_file = info.get("LOG_FILE")
                        latest_tps = info.get("T/s", 0.0)
                        if log_file and os.path.exists(log_file):
                            try:
                                import re
                                with open(log_file, "r", encoding="utf-8", errors="ignore") as lf:
                                    for line in reversed(lf.readlines()[-60:]):
                                        m_tps = re.search(r'([\d.]+)\s+(?:tokens per second|t/s)', line)
                                        if m_tps:
                                            parsed = float(m_tps.group(1))
                                            if 0.1 <= parsed <= 500:
                                                latest_tps = parsed
                                                break
                            except Exception:
                                pass
                        
                        active_model_info = {
                            "model": m_name,
                            "port": info.get("PORT", engine.port),
                            "pid": pid,
                            "tps": latest_tps,
                            "mode": info.get("MODE", "ram").upper(),
                            "ram": info.get("RAM", "")
                        }
                        break

        cpu_pct = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()

        emit({"req_id": req_id, "type": "response", "data": {
            "active_model": active_model_info,
            "port": active_model_info.get("port", engine.port),
            "system": {
                "cpu_percent": cpu_pct,
                "ram_total_gb": round(mem.total / (1024**3), 2),
                "ram_used_gb": round(mem.used / (1024**3), 2),
                "ram_percent": mem.percent
            }
        }})

    elif action == "launch_model":
        model_name = req.get("model")
        try:
            import launch_model
            loop = asyncio.get_event_loop()
            res = await loop.run_in_executor(None, launch_model.launchmodel, model_name)
            engine.refresh_port()
            emit({"req_id": req_id, "type": "response", "data": {
                "status": "launched",
                "model": model_name,
                "port": res.get("port") if res else None,
                "pid": res.get("pid") if res else None
            }})
        except Exception as e:
            emit({"req_id": req_id, "type": "error", "error": str(e)})

    elif action == "kill_model":
        target = req.get("model")
        target_pid = req.get("pid")
        killed_any = False
        try:
            import Smartswitch
            import psutil
            status_file = os.path.join(PROJECT_ROOT, "data", "status.txt")
            if os.path.exists(status_file):
                with open(status_file, "r", encoding="utf-8") as f:
                    try:
                        sdata = json.load(f)
                    except Exception:
                        sdata = {}
                
                # If specific model or PID given
                for k, info in list(sdata.items()):
                    p = info.get("PID")
                    if (target and (k == target or target in k)) or (target_pid and p == target_pid) or (not target and not target_pid):
                        if p:
                            Smartswitch.killprocess(p)
                            killed_any = True
                        del sdata[k]
                with open(status_file, "w", encoding="utf-8") as f:
                    json.dump(sdata, f, indent=4)
            
            # If PID directly provided but not in status.txt
            if target_pid and not killed_any:
                import Smartswitch
                Smartswitch.killprocess(int(target_pid))
                killed_any = True

            engine.refresh_port()
            emit({"req_id": req_id, "type": "response", "data": {"status": "killed", "success": killed_any}})
        except Exception as e:
            emit({"req_id": req_id, "type": "error", "error": str(e)})

    elif action == "trigger_smartswitch":
        # Launch fallback model on degraded model's port or base port
        base_model = req.get("base_model", "Qwen2.5-0.5B-Instruct-Q4_K_M")
        try:
            import launch_model
            import Smartswitch
            # Kill running models
            status_file = os.path.join(PROJECT_ROOT, "data", "status.txt")
            last_port = engine.port
            if os.path.exists(status_file):
                with open(status_file, "r", encoding="utf-8") as f:
                    try:
                        sdata = json.load(f)
                    except Exception:
                        sdata = {}
                for k, info in list(sdata.items()):
                    p = info.get("PID")
                    if p:
                        Smartswitch.killprocess(p)
                    last_port = info.get("PORT", last_port)
                with open(status_file, "w", encoding="utf-8") as f:
                    json.dump({}, f)

            time.sleep(1.0)
            loop = asyncio.get_event_loop()
            res = await loop.run_in_executor(None, launch_model.launchmodel, base_model, last_port)
            engine.refresh_port()
            emit({"req_id": req_id, "type": "response", "data": {
                "status": "switched",
                "model": base_model,
                "port": res.get("port") if res else last_port
            }})
        except Exception as e:
            emit({"req_id": req_id, "type": "error", "error": str(e)})

    elif action == "system_assess":
        try:
            import psutil
            mem = psutil.virtual_memory()
            cpu_count = psutil.cpu_count(logical=True)
            models_dir = os.path.join(PROJECT_ROOT, "models")
            model_evals = []

            # 1. Measure real TPS of currently active model if running
            active_real_tps = None
            try:
                engine.refresh_port()
                t0 = time.time()
                token_count = 0
                async for ev in engine.stream_chat(
                    messages=[{"role": "user", "content": "Count from 1 to 10 in numbers."}],
                    mode="chat",
                    max_tokens=25
                ):
                    if ev.get("type") == "message:delta":
                        token_count += 1
                dt = time.time() - t0
                if dt > 0 and token_count > 0:
                    active_real_tps = round(token_count / dt, 2)
            except Exception:
                active_real_tps = None

            # 2. Update status.txt with real measured TPS if available
            status_file = os.path.join(PROJECT_ROOT, "data", "status.txt")
            if active_real_tps and os.path.exists(status_file):
                try:
                    with open(status_file, "r", encoding="utf-8") as sf:
                        sdata = json.load(sf)
                    for k, inf in sdata.items():
                        if isinstance(inf, dict):
                            inf["T/s"] = active_real_tps
                    with open(status_file, "w", encoding="utf-8") as sf:
                        json.dump(sdata, sf, indent=4)
                except Exception:
                    pass

            if os.path.exists(models_dir):
                for f in os.listdir(models_dir):
                    if f.endswith(".gguf"):
                        size_mb = round(os.path.getsize(os.path.join(models_dir, f)) / (1024 * 1024), 1)
                        # If this is the active model, use the real benchmarked TPS
                        est_tps = active_real_tps if active_real_tps else round(max(5.0, 120.0 / (size_mb / 500.0)), 1)
                        model_evals.append({
                            "name": f[:-5],
                            "size_mb": size_mb,
                            "fits_ram": (size_mb * 1.3) < (mem.available / (1024 * 1024)),
                            "estimated_tps": est_tps,
                            "is_real_benchmark": bool(active_real_tps)
                        })

            emit({"req_id": req_id, "type": "response", "data": {
                "cpu_cores": cpu_count,
                "ram_total_gb": round(mem.total / (1024**3), 2),
                "ram_free_gb": round(mem.available / (1024**3), 2),
                "measured_tps": active_real_tps,
                "models": model_evals
            }})
        except Exception as e:
            emit({"req_id": req_id, "type": "error", "error": str(e)})

    elif action == "download_model":
        repo_id = req.get("repo_id")
        filename = req.get("filename")
        if not repo_id or not filename:
            emit({"req_id": req_id, "type": "error", "error": "Missing repo_id or filename"})
            return
        try:
            from huggingface_hub import hf_hub_download
            models_dir = os.path.join(PROJECT_ROOT, "models")
            loop = asyncio.get_event_loop()
            res_path = await loop.run_in_executor(
                None,
                lambda: hf_hub_download(repo_id=repo_id, filename=filename, local_dir=models_dir, resume_download=True)
            )
            emit({"req_id": req_id, "type": "response", "data": {"status": "downloaded", "path": res_path}})
        except Exception as e:
            emit({"req_id": req_id, "type": "error", "error": str(e)})

    elif action == "execute_code":
        code = req.get("code", "")
        try:
            import subprocess
            loop = asyncio.get_event_loop()
            def run_py():
                proc = subprocess.run(
                    [sys.executable, "-c", code],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    cwd=PROJECT_ROOT
                )
                output = proc.stdout
                if proc.stderr:
                    output += ("\n" if output else "") + proc.stderr
                return {"output": output or "(Executed with no output)", "exit_code": proc.returncode}
            
            result = await loop.run_in_executor(None, run_py)
            emit({"req_id": req_id, "type": "response", "data": result})
        except subprocess.TimeoutExpired:
            emit({"req_id": req_id, "type": "response", "data": {"output": "❌ Execution timed out (20s limit)", "exit_code": 124}})
        except Exception as e:
            emit({"req_id": req_id, "type": "error", "error": str(e)})

    elif action == "complete_code":
        prefix = req.get("prefix", "")
        max_tokens = int(req.get("max_tokens", 64))
        try:
            prompt = f"Complete the following code snippet cleanly. Output ONLY the code completion without explanation:\n\n{prefix}"
            completion_text = ""
            async for ev in engine.stream_chat(
                messages=[{"role": "user", "content": prompt}],
                mode="chat",
                temperature=0.2,
                max_tokens=max_tokens
            ):
                if ev.get("type") == "message:delta":
                    completion_text += ev.get("delta", "")
                elif ev.get("type") == "message:complete":
                    if ev.get("full_text"):
                        completion_text = ev.get("full_text")
            
            # Clean up markdown code blocks if the model wrapped it
            clean_comp = completion_text
            if clean_comp.startswith("```python"):
                clean_comp = clean_comp[9:]
            elif clean_comp.startswith("```"):
                clean_comp = clean_comp[3:]
            if clean_comp.endswith("```"):
                clean_comp = clean_comp[:-3]
            
            emit({"req_id": req_id, "type": "response", "data": {"completion": clean_comp}})
        except Exception as e:
            emit({"req_id": req_id, "type": "error", "error": str(e)})

    elif action == "rag_ingest":
        text = req.get("text", "")
        filename = req.get("filename", "custom_document.txt")
        try:
            import rag
            from langchain_core.documents import Document
            db_dir = os.path.join(PROJECT_ROOT, "chroma_db")
            db = rag.Database(persist_directory=db_dir)
            wrapper = rag.TextLoaderWrapper()
            docs = [Document(page_content=text, metadata={"source": filename})]
            chunks = wrapper.chunk_text(docs, chunk_size=500, overlap=50)
            hash_id = rag.stopdeduplication(text)
            db.create_vectorstore(chunks, hash_id=hash_id)
            emit({"req_id": req_id, "type": "response", "data": {
                "status": "ingested",
                "filename": filename,
                "chunks": len(chunks)
            }})
        except Exception as e:
            emit({"req_id": req_id, "type": "error", "error": str(e)})

    elif action == "list_tools":
        tools_dir = os.path.join(PROJECT_ROOT, "Tools")
        tools = []
        if os.path.exists(tools_dir):
            for f in sorted(os.listdir(tools_dir)):
                if f.endswith(".py") and not f.startswith("__"):
                    name = f[:-3]
                    desc = ""
                    try:
                        with open(os.path.join(tools_dir, f), "r", encoding="utf-8") as tf:
                            lines = [tf.readline() for _ in range(5)]
                            desc = "".join(lines).strip()
                    except Exception:
                        pass
                    tools.append({"name": name, "file": f, "description": desc})
        emit({"req_id": req_id, "type": "response", "data": tools})

    elif action == "create_tool":
        tool_name = req.get("name", "").strip().replace(" ", "_")
        code = req.get("code", "")
        desc = req.get("description", "Custom user-defined tool")
        if not tool_name:
            emit({"req_id": req_id, "type": "error", "error": "Missing tool name"})
            return
        try:
            tools_dir = os.path.join(PROJECT_ROOT, "Tools")
            os.makedirs(tools_dir, exist_ok=True)
            tool_path = os.path.join(tools_dir, f"{tool_name}.py")
            header = f"# Tools/{tool_name}.py\n# name: {tool_name}\n# description: {desc}\n\n"
            full_code = header + code if not code.startswith("# Tools/") else code
            with open(tool_path, "w", encoding="utf-8") as tf:
                tf.write(full_code)
            emit({"req_id": req_id, "type": "response", "data": {"status": "created", "name": tool_name, "file": f"{tool_name}.py"}})
        except Exception as e:
            emit({"req_id": req_id, "type": "error", "error": str(e)})

    elif action == "delete_tool":
        tool_name = req.get("name", "")
        try:
            tools_dir = os.path.join(PROJECT_ROOT, "Tools")
            target = os.path.join(tools_dir, f"{tool_name}.py" if not tool_name.endswith(".py") else tool_name)
            if os.path.exists(target):
                os.remove(target)
                emit({"req_id": req_id, "type": "response", "data": {"status": "deleted", "name": tool_name}})
            else:
                emit({"req_id": req_id, "type": "error", "error": "Tool not found"})
        except Exception as e:
            emit({"req_id": req_id, "type": "error", "error": str(e)})

    else:
        emit({"req_id": req_id, "type": "error", "error": f"Unknown action: {action}"})


async def main():
    # Signal readiness to Electron
    emit({"type": "bridge:ready", "timestamp": datetime.now().isoformat()})

    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        line = await reader.readline()
        if not line:
            break
        try:
            line_str = line.decode("utf-8")
            await process_command(line_str)
        except Exception as e:
            logger.exception("Error processing line")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
