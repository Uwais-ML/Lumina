"""
app/backend/streaming_service.py - Real-time asynchronous streaming engine for Lumina.

Provides:
- Asynchronous OpenAI streaming with stream=True using AsyncOpenAI.
- RAG document context retrieval and stream integration.
- Agentic multi-step tool execution with incremental feedback and streaming.
- Conversation persistence and context memory tracking.
"""

import os
import sys
import json
import time
import uuid
import re
import asyncio
import logging
from typing import AsyncGenerator, Dict, Any, List, Optional
from datetime import datetime

# Path setup to import existing Lumina scripts and dependencies
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(BACKEND_DIR)
PROJECT_ROOT = os.path.dirname(APP_DIR)

# Ensure site-packages and scripts are in sys.path
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

from openai import AsyncOpenAI

# Setup logging
logger = logging.getLogger("LuminaStream")
logger.setLevel(logging.INFO)

CONVERSATIONS_FILE = os.path.join(PROJECT_ROOT, "data", "conversations.json")
STATUS_FILE = os.path.join(PROJECT_ROOT, "data", "status.txt")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)


class ConversationStore:
    """Manages persistent conversations on disk."""
    
    @staticmethod
    def load_all() -> List[Dict[str, Any]]:
        if not os.path.exists(CONVERSATIONS_FILE):
            return []
        try:
            with open(CONVERSATIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Failed to load conversations: {e}")
            return []

    @staticmethod
    def save_all(conversations: List[Dict[str, Any]]):
        try:
            with open(CONVERSATIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(conversations, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save conversations: {e}")

    @classmethod
    def get(cls, conv_id: str) -> Optional[Dict[str, Any]]:
        convs = cls.load_all()
        for c in convs:
            if c.get("id") == conv_id:
                return c
        return None

    @classmethod
    def save(cls, conversation: Dict[str, Any]):
        convs = cls.load_all()
        found = False
        for i, c in enumerate(convs):
            if c.get("id") == conversation.get("id"):
                convs[i] = conversation
                found = True
                break
        if not found:
            convs.insert(0, conversation)
        cls.save_all(convs)

    @classmethod
    def delete(cls, conv_id: str) -> bool:
        convs = cls.load_all()
        initial_len = len(convs)
        convs = [c for c in convs if c.get("id") != conv_id]
        if len(convs) != initial_len:
            cls.save_all(convs)
            return True
        return False


def get_active_model_port() -> int:
    """Reads active model port from status.txt or probes active local llamafile ports."""
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    # Check direct key
                    if "port" in data:
                        return int(data["port"])
                    # Check Smartswitch multi-model dictionary format:
                    # {"ModelName": {"PORT": 53768, "PID": 1234, ...}}
                    for model_name, info in reversed(list(data.items())):
                        if isinstance(info, dict) and "PORT" in info:
                            return int(info["PORT"])
        except Exception:
            pass
    return 54993


class LuminaStreamEngine:
    """Asynchronous streaming engine for Lumina."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.port = get_active_model_port()
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL") or f"http://127.0.0.1:{self.port}/v1"
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or "EMPTY"
        self._init_client()

    def _init_client(self):
        self.client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=120.0
        )

    def refresh_port(self):
        new_port = get_active_model_port()
        if new_port != self.port:
            self.port = new_port
            if "127.0.0.1" in self.base_url or "localhost" in self.base_url:
                self.base_url = f"http://127.0.0.1:{self.port}/v1"
                self._init_client()

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        mode: str = "chat",
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        conversation_id: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Asynchronously streams LLM responses with real-time events:
        - message:start
        - message:status
        - message:delta
        - message:tool
        - message:complete
        - message:error
        """
        self.refresh_port()
        msg_id = f"msg_{uuid.uuid4().hex[:12]}"
        model_name = model or "qwen"

        yield {
            "type": "message:start",
            "id": msg_id,
            "conversation_id": conversation_id,
            "model": model_name,
            "mode": mode,
            "timestamp": datetime.now().isoformat()
        }

        user_query = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_query = m.get("content", "")
                break

        full_content = ""
        sources = []
        tools_executed = []

        try:
            # ── 1. RAG Mode ──────────────────────────────────────────────────
            if mode == "rag":
                yield {
                    "type": "message:status",
                    "status": "retrieving",
                    "detail": "Searching document vector store for relevant context..."
                }

                rag_context, retrieved_sources = await self._retrieve_rag_context(user_query)
                sources = retrieved_sources

                if rag_context:
                    yield {
                        "type": "message:status",
                        "status": "thinking",
                        "detail": f"Synthesizing response from {len(sources)} document chunk(s)..."
                    }
                    augmented_messages = list(messages)
                    system_prompt = (
                        "You are Lumina, an intelligent desktop AI assistant.\n"
                        "Answer the question strictly and accurately using the context provided below.\n"
                        "Cite chunk IDs or sources where appropriate.\n"
                        "If the context does not contain the answer, state that clearly.\n\n"
                        f"--- CONTEXT ---\n{rag_context}\n--- END CONTEXT ---"
                    )
                    # Prepend or replace system message
                    if augmented_messages and augmented_messages[0].get("role") == "system":
                        augmented_messages[0] = {"role": "system", "content": system_prompt}
                    else:
                        augmented_messages.insert(0, {"role": "system", "content": system_prompt})
                    
                    messages = augmented_messages

            # ── 2. Agentic Mode ──────────────────────────────────────────────
            elif mode == "agentic":
                yield {
                    "type": "message:status",
                    "status": "thinking",
                    "detail": "Analyzing task and evaluating available tools..."
                }

                # Run tool classification & multi-step execution if needed
                agent_result = await self._execute_agentic_flow(user_query, messages)
                if agent_result.get("tools_executed"):
                    tools_executed = agent_result["tools_executed"]
                    for t in tools_executed:
                        yield {
                            "type": "message:tool",
                            "tool": t["tool"],
                            "args": t["args"],
                            "result": t["result"]
                        }
                    
                    # Provide synthesis with tool outputs
                    yield {
                        "type": "message:status",
                        "status": "generating",
                        "detail": "Generating final response with tool results..."
                    }
                    system_prompt = (
                        "You are Lumina, an autonomous desktop AI agent.\n"
                        "Summarize the completed actions and output the final result clearly for the user."
                    )
                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Task: {user_query}\n\nActions Performed:\n{agent_result.get('summary', '')}"}
                    ]

            # ── 3. Model Generation (Direct Token Streaming) ─────────────────
            yield {
                "type": "message:status",
                "status": "generating",
                "detail": "Lumina is generating..."
            }

            stream = await self.client.chat.completions.create(
                model=model_name,
                messages=messages,
                stream=True,
                temperature=temperature,
                max_tokens=max_tokens
            )

            async for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    content_delta = getattr(delta, "content", "") or ""
                    if content_delta:
                        full_content += content_delta
                        yield {
                            "type": "message:delta",
                            "id": msg_id,
                            "delta": content_delta
                        }

            # ── 4. Complete Event ────────────────────────────────────────────
            yield {
                "type": "message:complete",
                "id": msg_id,
                "full_text": full_content,
                "sources": sources,
                "tools": tools_executed,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            err_msg = str(e)
            if "ConnectError" in err_msg or "APIConnectionError" in type(e).__name__:
                err_msg = (
                    f"Lumina local model is not currently reachable on {self.base_url}. "
                    "Please launch a model from the Models panel or verify that a model server is running."
                )
            logger.exception("Error during streaming generation")
            yield {
                "type": "message:error",
                "id": msg_id,
                "error": err_msg,
                "partial_text": full_content
            }

    async def _retrieve_rag_context(self, query: str) -> tuple[str, List[str]]:
        """Retrieves matching chunks from Chroma DB vector store."""
        try:
            import rag
            db_dir = os.path.join(PROJECT_ROOT, "chroma_db")
            if not os.path.exists(db_dir):
                return "", []
            
            db = rag.Database(persist_directory=db_dir)
            vectorstore = db.load_vectorstore()
            if not vectorstore:
                return "", []

            docs = db.query_vectorsearch(vectorstore, query, k=3, search_type="similarity")
            if not docs:
                return "", []

            context_parts = []
            sources = []
            for i, doc in enumerate(docs):
                src = doc.metadata.get("source", f"Chunk {i+1}")
                sources.append(src)
                context_parts.append(f"[{src}]: {doc.page_content}")

            return "\n\n".join(context_parts), sources
        except Exception as e:
            logger.warning(f"RAG retrieval error (falling back to direct): {e}")
            return "", []

    async def _execute_agentic_flow(self, query: str, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """Runs autonomous tool execution and returns action logs."""
        tools_executed = []
        summary = ""

        try:
            tools_dir = os.path.join(PROJECT_ROOT, "Tools")
            if not os.path.exists(tools_dir):
                return {"tools_executed": [], "summary": "No tools directory available."}

            # List available tools
            available_tools = []
            for f in sorted(os.listdir(tools_dir)):
                if f.endswith(".py") and not f.startswith("__"):
                    tool_name = f[:-3]
                    filepath = os.path.join(tools_dir, f)
                    doc = ""
                    try:
                        with open(filepath, "r", encoding="utf-8") as tf:
                            lines = [tf.readline() for _ in range(6)]
                            doc = "".join(lines).strip()
                    except Exception:
                        pass
                    available_tools.append(f"{tool_name}: {doc[:100]}")

            tools_spec = "\n".join(available_tools)

            # Ask model to pick a tool if needed
            plan_prompt = (
                f"You have these Python tools available in Tools/:\n{tools_spec}\n\n"
                f"User request: {query}\n"
                "If a tool is needed to answer this request, specify the exact tool call in the format: tool_name(arg1, arg2).\n"
                "If no tool is required, reply: NONE"
            )

            completion = await self.client.chat.completions.create(
                model="qwen",
                messages=[
                    {"role": "system", "content": "You are a tool dispatcher. Output tool calls or NONE."},
                    {"role": "user", "content": plan_prompt}
                ],
                temperature=0.1,
                max_tokens=150
            )

            decision = completion.choices[0].message.content.strip()
            match = re.search(r'(\w+)\((.*)\)', decision)

            if match and "none" not in decision.lower():
                tool_name, args_str = match.groups()
                tool_path = os.path.join(tools_dir, f"{tool_name}.py")

                if os.path.exists(tool_path):
                    # Parse args
                    raw_args = [a.strip().strip("'\"") for a in args_str.split(",") if a.strip()]
                    
                    # Resolve python interpreter
                    from agentic_rag import get_bundled_python
                    python_bin = get_bundled_python()
                    
                    cmd = [python_bin, tool_path] + raw_args
                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
                    output = stdout.decode("utf-8", errors="replace").strip()
                    err = stderr.decode("utf-8", errors="replace").strip()

                    result_text = output if proc.returncode == 0 else f"Error: {err or output}"
                    tools_executed.append({
                        "tool": tool_name,
                        "args": raw_args,
                        "result": result_text
                    })
                    summary = f"Executed {tool_name}({args_str})\nResult: {result_text}"

            return {
                "tools_executed": tools_executed,
                "summary": summary
            }

        except Exception as e:
            logger.error(f"Agentic flow error: {e}")
            return {"tools_executed": tools_executed, "summary": f"Tool execution failed: {e}"}
