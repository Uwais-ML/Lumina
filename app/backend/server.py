"""
app/backend/server.py - Lumina Asynchronous Backend Server.

Provides:
- Real-time Server-Sent Events (SSE) token streaming via /api/chat/stream.
- Complete REST APIs for conversations, models, RAG documents, and system metrics.
- Background process supervisor and health checks.
"""

import os
import sys
import json
import logging
import asyncio
from datetime import datetime
from aiohttp import web

# Path setup
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("LuminaServer")

# Global engine instance
stream_engine = LuminaStreamEngine()


# ── Middleware for CORS ──────────────────────────────────────────────────────
@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        response = web.Response(status=204)
    else:
        try:
            response = await handler(request)
        except web.HTTPException as ex:
            response = ex

    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


# ── Route Handlers ───────────────────────────────────────────────────────────

async def handle_health(request):
    """Health check endpoint."""
    stream_engine.refresh_port()
    status_file = os.path.join(PROJECT_ROOT, "data", "status.txt")
    model_status = {}
    if os.path.exists(status_file):
        try:
            with open(status_file, "r", encoding="utf-8") as f:
                model_status = json.load(f)
        except Exception:
            pass

    return web.json_response({
        "status": "ok",
        "service": "Lumina Backend",
        "port": stream_engine.port,
        "base_url": stream_engine.base_url,
        "model_status": model_status,
        "timestamp": datetime.now().isoformat()
    })


async def handle_chat_stream(request):
    """Server-Sent Events streaming endpoint for real-time model output."""
    try:
        data = await request.json()
    except Exception:
        data = {}

    conversation_id = data.get("conversation_id")
    messages = data.get("messages", [])
    mode = data.get("mode", "chat")
    model = data.get("model", "qwen")
    temperature = float(data.get("temperature", 0.7))
    max_tokens = int(data.get("max_tokens", 2048))

    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "X-Accel-Buffering": "no"
        }
    )
    await response.prepare(request)

    full_response_text = ""
    complete_event_data = None

    try:
        async for event in stream_engine.stream_chat(
            messages=messages,
            mode=mode,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            conversation_id=conversation_id
        ):
            event_type = event.get("type", "message")
            event_payload = json.dumps(event, ensure_ascii=False)
            sse_chunk = f"event: {event_type}\ndata: {event_payload}\n\n".encode("utf-8")
            await response.write(sse_chunk)

            if event_type == "message:delta":
                full_response_text += event.get("delta", "")
            elif event_type == "message:complete":
                complete_event_data = event

        # Auto-persist conversation if conversation_id was provided
        if conversation_id and full_response_text:
            conv = ConversationStore.get(conversation_id)
            if not conv:
                # Create title from first user message
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
            
            # Append assistant message
            assistant_msg = {
                "id": complete_event_data.get("id") if complete_event_data else f"msg_{int(time.time())}",
                "role": "assistant",
                "content": full_response_text,
                "sources": complete_event_data.get("sources", []) if complete_event_data else [],
                "tools": complete_event_data.get("tools", []) if complete_event_data else [],
                "timestamp": datetime.now().isoformat()
            }
            conv_messages = [m for m in messages if m.get("role") != "assistant"]
            conv_messages.append(assistant_msg)
            conv["messages"] = conv_messages
            conv["updated_at"] = datetime.now().isoformat()
            ConversationStore.save(conv)

    except (asyncio.CancelledError, ConnectionResetError):
        logger.info("Client disconnected during stream")
    except Exception as e:
        logger.exception("Error in SSE stream")
        err_chunk = f"event: message:error\ndata: {json.dumps({'error': str(e)})}\n\n".encode("utf-8")
        try:
            await response.write(err_chunk)
        except Exception:
            pass

    return response


async def handle_list_conversations(request):
    """Returns all conversations ordered by recent activity."""
    convs = ConversationStore.load_all()
    summaries = []
    for c in convs:
        summaries.append({
            "id": c.get("id"),
            "title": c.get("title", "Untitled Chat"),
            "created_at": c.get("created_at"),
            "updated_at": c.get("updated_at"),
            "message_count": len(c.get("messages", [])),
            "mode": c.get("mode", "chat")
        })
    return web.json_response(summaries)


async def handle_get_conversation(request):
    """Retrieves a single conversation by ID."""
    conv_id = request.match_info["id"]
    conv = ConversationStore.get(conv_id)
    if not conv:
        return web.json_response({"error": "Conversation not found"}, status=404)
    return web.json_response(conv)


async def handle_save_conversation(request):
    """Creates or updates a conversation."""
    data = await request.json()
    conv_id = data.get("id")
    if not conv_id:
        return web.json_response({"error": "Missing conversation id"}, status=400)
    
    ConversationStore.save(data)
    return web.json_response({"status": "saved", "id": conv_id})


async def handle_delete_conversation(request):
    """Deletes a conversation."""
    conv_id = request.match_info["id"]
    success = ConversationStore.delete(conv_id)
    return web.json_response({"status": "deleted" if success else "not_found", "id": conv_id})


async def handle_list_models(request):
    """Returns local GGUF models on disk and catalog models."""
    models_dir = os.path.join(PROJECT_ROOT, "models")
    local_models = []
    if os.path.isdir(models_dir):
        for f in os.listdir(models_dir):
            if f.endswith(".gguf"):
                path = os.path.join(models_dir, f)
                size_mb = round(os.path.getsize(path) / (1024 * 1024), 1)
                local_models.append({
                    "name": f[:-5],
                    "filename": f,
                    "size_mb": size_mb,
                    "path": path
                })

    # Catalog from llmstore.json
    store_file = os.path.join(PROJECT_ROOT, "resources", "llmstore.json")
    catalog = []
    if os.path.exists(store_file):
        try:
            with open(store_file, "r", encoding="utf-8") as f:
                catalog = json.load(f)
        except Exception:
            pass

    return web.json_response({
        "local": local_models,
        "catalog": catalog
    })


async def handle_launch_model(request):
    """Launches a local GGUF model via scripts/launch_model.py."""
    data = await request.json()
    model_name = data.get("model")
    if not model_name:
        return web.json_response({"error": "Missing model parameter"}, status=400)

    try:
        import launch_model
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, launch_model.launchmodel, model_name)
        stream_engine.refresh_port()
        return web.json_response({
            "status": "launched",
            "model": model_name,
            "port": res.get("port"),
            "pid": res.get("pid")
        })
    except Exception as e:
        logger.exception("Failed to launch model")
        return web.json_response({"error": str(e)}, status=500)


async def handle_get_status(request):
    """Returns current system and inference status."""
    status_file = os.path.join(PROJECT_ROOT, "data", "status.txt")
    status_data = {}
    if os.path.exists(status_file):
        try:
            with open(status_file, "r", encoding="utf-8") as f:
                status_data = json.load(f)
        except Exception:
            pass

    import psutil
    cpu_pct = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()

    return web.json_response({
        "active_model": status_data,
        "system": {
            "cpu_percent": cpu_pct,
            "ram_total_gb": round(mem.total / (1024**3), 2),
            "ram_used_gb": round(mem.used / (1024**3), 2),
            "ram_percent": mem.percent
        }
    })


async def handle_list_tools(request):
    """Returns available tools in the Tools/ directory."""
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
    return web.json_response(tools)


async def handle_rag_ingest(request):
    """Ingests text content into Chroma DB vector store."""
    data = await request.json()
    text = data.get("text", "")
    filename = data.get("filename", "custom_document.txt")

    if not text.strip():
        return web.json_response({"error": "Empty content"}, status=400)

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

        return web.json_response({
            "status": "ingested",
            "filename": filename,
            "chunks_created": len(chunks)
        })
    except Exception as e:
        logger.exception("RAG ingestion error")
        return web.json_response({"error": str(e)}, status=500)


def create_app():
    """Initializes and returns the aiohttp application."""
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get("/health", handle_health)
    app.router.add_post("/api/chat/stream", handle_chat_stream)
    app.router.add_get("/api/conversations", handle_list_conversations)
    app.router.add_get("/api/conversations/{id}", handle_get_conversation)
    app.router.add_post("/api/conversations", handle_save_conversation)
    app.router.add_delete("/api/conversations/{id}", handle_delete_conversation)
    app.router.add_get("/api/models", handle_list_models)
    app.router.add_post("/api/models/launch", handle_launch_model)
    app.router.add_get("/api/status", handle_get_status)
    app.router.add_get("/api/tools", handle_list_tools)
    app.router.add_post("/api/rag/ingest", handle_rag_ingest)
    return app


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Lumina Asynchronous Streaming Server")
    parser.add_argument("--port", type=int, default=7788, help="Server port (default: 7788)")
    parser.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    args = parser.parse_args()

    app = create_app()
    logger.info(f"✨ Starting Lumina Streaming Server on http://{args.host}:{args.port}")
    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
