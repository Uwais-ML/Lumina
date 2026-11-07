import os
import warnings
warnings.filterwarnings("ignore")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")

import logging
import classifier
import requests
import platform
import subprocess
import re
import sys
import asyncio
import argparse

# ── Bundled Python resolver (mirrors Lumina.py cross-platform detection) ──────
_SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
folder_path = os.path.join(_PROJECT_ROOT, "Tools")
os.makedirs(folder_path, exist_ok=True)


def get_bundled_python() -> str:
    """
    Locate the bundled CPython interpreter for the current OS.
    Falls back to sys.executable when the bundled runtime is absent
    (e.g. during development without the full distribution).

    Mirrors the detection logic in Lumina.py so all tool sub-processes
    run inside the same isolated CPython env across macOS / Windows / Linux.
    """
    system = platform.system().lower()

    if "darwin" in system or "mac" in system:
        bin_path = os.path.join(
            _PROJECT_ROOT, "python-dependencies", "macos-intel", "bin", "python3"
        )
    elif system.startswith("win"):
        bin_path = os.path.join(
            _PROJECT_ROOT, "python-dependencies", "windows", "python.exe"
        )
    else:  # Linux / other POSIX
        bin_path = os.path.join(
            _PROJECT_ROOT, "python-dependencies", "linux-intel", "bin", "python3"
        )

    if os.path.exists(bin_path):
        return bin_path

    # Graceful fallback – keeps agentic working in dev / CI environments
    logging.debug(
        "[Agentic] Bundled Python not found at %s — falling back to sys.executable (%s)",
        bin_path, sys.executable,
    )
    return sys.executable
# ─────────────────────────────────────────────────────────────────────────────


def argparser():
    """Build and return argument parser."""
    parser = argparse.ArgumentParser(
        prog="agentic",
        description="Lumina Agentic AI — autonomous agent system that chains multiple tools\n"
                    "to solve complex queries. Monitors LLM responses and executes tool calls\n"
                    "in sequence until task completion.\n\n"
                    "Supports: file operations, data processing, web search, calculations,\n"
                    "text transformations, and custom tools via Python execution.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  # Simple query\n"
               "  python agentic.py --query 'Save pytorch info to file'\n\n"
               "  # Full control\n"
               "  python agentic.py \\\n"
               "    -q 'Delete old file, create new one, read it back' \\\n"
               "    -p 54993 -i 10 -t 0.2\n\n"
               "  # With model selection\n"
               "  python agentic.py \\\n"
               "    -q 'Search and summarize machine learning' \\\n"
               "    -p 54993 -m qwen -i 15 --verbose"
    )
    
    parser.add_argument(
        "--query",
        "-q",
        required=True,
        metavar="TEXT",
        help="The task/query for the agent to execute (required)",
    )
    
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=54993,
        metavar="N",
        help="LLM API port (default: 54993)",
    )
    
    parser.add_argument(
        "--model",
        "-m",
        default="qwen",
        metavar="NAME",
        help="LLM model name (default: qwen)",
    )
    
    parser.add_argument(
        "--temperature",
        "-t",
        type=float,
        default=0.2,
        metavar="N",
        help="LLM temperature 0–1, lower=deterministic (default: 0.2)",
    )
    
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=256,
        metavar="N",
        help="Max tokens per LLM response (default: 256)",
    )
    
    parser.add_argument(
        "--iterations",
        "-i",
        type=int,
        default=5,
        metavar="N",
        help="Maximum tool execution iterations (default: 5)",
    )
    
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Enable verbose output",
    )
    
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        metavar="N",
        help="Timeout in seconds for LLM query (default: 120)",
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    
    return parser  # ← IMPORTANT: Return the parser!


def get_all_tools(compact=True):
    """Returns clean, concise summaries of all available tools for prompt efficiency."""
    abs_folder = os.path.abspath(folder_path)
    if not os.path.exists(abs_folder):
        return None

    tool_lines = []
    for filename in sorted(os.listdir(abs_folder)):
        filepath = os.path.join(abs_folder, filename)
        if os.path.isfile(filepath) and filename.endswith('.py'):
            t_name = filename[:-3]
            desc = ""
            args = ""
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                for _ in range(8):
                    line = f.readline()
                    if not line:
                        break
                    if line.startswith("# description:"):
                        desc = line.split(":", 1)[1].strip()
                    elif line.startswith("# arguments:"):
                        args = line.split(":", 1)[1].strip()

            if desc and args:
                tool_lines.append(f"- {t_name}({args}): {desc}")
            elif desc:
                tool_lines.append(f"- {t_name}(): {desc}")
            else:
                tool_lines.append(f"- {t_name}()")

    return "\n".join(tool_lines) if tool_lines else None


def classifyiftoolsneeded(query, timeout=60, skip_classifier=True):
    """Classify if tools needed. Defaults to compact tools without spawning secondary processes."""
    if skip_classifier:
        return get_all_tools()

    try:
        port = classifier.initialize()
        if classifier.Model_status and port is not None:
            import Smartswitch
            payload = {
                "model": "qwen",
                "temperature": 0,
                "max_tokens": 50,
                "messages": [
                    {"role": "system", "content": "Answer only: tools or not_tools"},
                    {"role": "user", "content": f"{query}"}
                ]
            }
            response = Smartswitch.safe_query(port, payload=payload, timeout=timeout)
            if response is not None and response.status_code == 200:
                decision = response.json()["choices"][0]["message"]["content"].strip().lower()
                if "not_tools" in decision or "not tools" in decision:
                    return None
    except Exception as e:
        logging.warning(f"Classification skipped or failed ({e}); falling back to tools.")

    return get_all_tools()


def extract_tool_calls(text: str):
    """
    Robust multi-pattern extractor for tool calls:
    1. Looks for 'Action: toolname(...)' or 'Action: ```toolname(...)```'
    2. Strips markdown fences, e.g. ```python toolname(...) ```
    3. Finds standard toolname(arg1, arg2, ...) anywhere in the text
    4. Handles 'Tool: toolname' and 'Arguments: args' blocks
    """
    calls = []
    # Strip markdown backticks
    clean_text = re.sub(r'```(?:python|bash|json)?', '', text)
    clean_text = clean_text.replace('```', '')

    # 1. Action: tool_name(...)
    action_matches = re.findall(r'(?:Action|Call):\s*([a-zA-Z_]\w*\s*\(.*?\))', clean_text, re.DOTALL | re.IGNORECASE)
    for m in action_matches:
        calls.append(m.strip())

    # 2. Direct regex search for known tools or general func calls
    if not calls:
        direct_matches = re.findall(r'(\b[a-zA-Z_]\w*\s*\([^()]*?\))', clean_text)
        for m in direct_matches:
            # Exclude programming language constructs or examples
            prefix = m.split('(', 1)[0].strip().lower()
            if prefix not in ('print', 'if', 'while', 'for', 'def', 'return', 'class', 'example'):
                calls.append(m.strip())

    # 3. Tool: / Argument: key-value pattern
    if not calls:
        tool_m = re.search(r'Tool:\s*([a-zA-Z_]\w*)', clean_text, re.IGNORECASE)
        arg_m = re.search(r'Argument(?:s)?:\s*(.+)', clean_text, re.IGNORECASE)
        if tool_m and arg_m:
            t_name = tool_m.group(1).strip()
            t_args = arg_m.group(1).strip()
            calls.append(f"{t_name}({t_args})")

    return calls


def execute_tool(tool_call: str, max_obs_chars: int = 800):
    """
    Execute tool directly with argument parsing, error recovery,
    and observation windowing to prevent context window explosion.
    """
    try:
        print(f"\n[EXEC] Input: {tool_call}")
        clean_call = tool_call.strip()
        # Handle trailing semicolons or periods
        clean_call = re.sub(r'[;\.]+$', '', clean_call)

        match = re.match(r'([a-zA-Z_]\w*)\s*\((.*)\)', clean_call, re.DOTALL)
        if not match:
            return "Error: Invalid tool format. Must be: toolname(arg1, arg2)"

        tool_name, args_str = match.groups()
        print(f"[EXEC] Tool: {tool_name}, Args: {args_str}")

        # Parse arguments cleanly handling commas inside quotes
        import csv
        try:
            parsed = next(csv.reader([args_str.replace('\n', ' ')], skipinitialspace=True))
            args = [a.strip() for a in parsed]
        except Exception:
            args = [arg.strip() for arg in args_str.split(',')]

        clean_args = []
        for arg in args:
            if (arg.startswith('"') and arg.endswith('"')) or (arg.startswith("'") and arg.endswith("'")):
                arg = arg[1:-1]
            clean_args.append(arg)
        args = clean_args

        print(f"[EXEC] Parsed args: {args}")

        # Find tool file
        tool_file = os.path.join(folder_path, f"{tool_name}.py")
        if not os.path.exists(tool_file):
            return f"Error: Tool '{tool_name}' not found. Check available tools."

        # Execute using bundled CPython
        python_bin = get_bundled_python()
        cmd = [python_bin, tool_file] + args
        print(f"[EXEC] Running: {' '.join(cmd)}")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            out = result.stdout.strip()
            if len(out) > max_obs_chars:
                out = out[:max_obs_chars] + f"\n... [Truncated {len(out) - max_obs_chars} chars for context efficiency]"
            return out
        else:
            err = result.stderr.strip() or result.stdout.strip()
            return f"Error during {tool_name} execution: {err}"

    except subprocess.TimeoutExpired:
        return f"Error: Execution of {tool_call} timed out after 30 seconds."
    except Exception as e:
        return f"Error executing {tool_call}: {str(e)}"


async def agentic(query, port, model="qwen", iterations=6, temp=0.1, max_tokens=384, verbose=False, timeout=120):
    """
    Upgraded ReAct Agentic Loop:
    1. Enforces Thought -> Action -> Observation reasoning sequence.
    2. Multi-pattern tool parser (handles markdown, direct calls, JSON).
    3. Self-correcting reflection when tool execution encounters errors.
    4. Observation windowing (caps tool output at 800 chars to avoid memory thrashing).
    5. Clean Final Answer termination contract.
    """
    if verbose:
        print(f"\n[AGENTIC] Starting with query: {query}")
        print(f"[AGENTIC] Model: {model} · Port: {port} · Iterations: {iterations}")

    tools = classifyiftoolsneeded(query, timeout=min(timeout, 60))
    if not tools:
        # Fall back to all tools so agent is never blind
        tools = get_all_tools()

    if not tools:
        return {"status": "no_tools_found", "query": query}

    if verbose:
        print(f"[AGENTIC] Tools active:\n{tools}\n")

    system_prompt = f"""You are Lumina Agent, an autonomous problem-solving AI.
You solve tasks step-by-step using a ReAct (Reasoning + Action) protocol.

AVAILABLE TOOLS:
{tools}

PROTOCOL RULES:
1. For each step, think about what to do, then output your action in this format:
Thought: <explain why you need this tool and what arguments to use>
Action: toolname("arg1", "arg2")

2. Once you receive the Observation from the tool and the task is finished, output:
Thought: I have verified the result and completed the task.
Final Answer: <concise summary of what was accomplished>

3. If an action fails with an error, reflect on why it failed in your Thought and adjust your arguments.
4. Output ONLY the Thought and Action (or Final Answer). Do not write conversational filler."""

    history_log = ""
    iteration_count = 0

    while iterations > 0:
        iteration_count += 1
        try:
            if verbose:
                print(f"\n[LOOP] Iteration {iteration_count}")

            user_content = f"Task: {query}"
            if history_log:
                user_content += f"\n\nExecuted History:\n{history_log}\n\nWhat is your next Thought and Action?"

            import Smartswitch
            payload = {
                "model": model,
                "temperature": temp,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ]
            }

            response = Smartswitch.safe_query(port, payload=payload, timeout=timeout)
            if response is None or response.status_code != 200:
                print(f"[!] Warning: Query to port {port} failed or timed out during agent loop.")
                break

            full_response = response.json()["choices"][0]["message"]["content"].strip()
            if verbose:
                print(f"[LLM] Response:\n{full_response}")

            # Check if agent declared Final Answer
            if "Final Answer:" in full_response:
                answer = full_response.split("Final Answer:", 1)[1].strip()
                if verbose:
                    print(f"[AGENTIC] Task complete with Final Answer!")
                return {
                    "status": "success",
                    "final_answer": answer,
                    "history": history_log,
                    "iterations_used": iteration_count
                }

            # Extract tool calls
            tool_calls = extract_tool_calls(full_response)

            if not tool_calls:
                # If no tool call found, check if model says it's done
                if "DONE" in full_response.upper() or "TASK COMPLETE" in full_response.upper():
                    return {
                        "status": "success",
                        "final_answer": full_response,
                        "history": history_log,
                        "iterations_used": iteration_count
                    }
                # Prompt the agent to take action
                history_log += f"\nThought: {full_response}\nObservation: No valid Action detected. Please output 'Action: toolname(args)' or 'Final Answer: ...'."
                iterations -= 1
                continue

            executed_any = False
            for tc in tool_calls:
                print(f"[LLM] Calling: {tc}")
                obs = execute_tool(tc)
                print(f"[RESULT] {obs}")

                # Self-correction guidance if error
                if obs.startswith("Error:"):
                    obs_feedback = f"{obs} (Please reflect on this error and adjust arguments or tool)."
                else:
                    obs_feedback = obs

                history_log += f"\nAction: {tc}\nObservation: {obs_feedback}"
                executed_any = True

            # If task was a write/save and succeeded, check if we can conclude
            if executed_any and ("Successfully saved" in history_log or "Success:" in history_log):
                # Verify if agent feels satisfied
                pass

            iterations -= 1

        except Exception as e:
            print(f"[ERROR] {e}")
            logging.error(f"Agentic loop error: {e}")
            return {
                "status": "error",
                "message": str(e),
                "partial_history": history_log
            }

    return {
        "status": "completed_max_iterations",
        "result": history_log,
        "iterations_used": iteration_count
    }


if __name__ == "__main__":
  
    parser = argparser()
    args = parser.parse_args()
    

    logging.basicConfig(level=getattr(logging, args.log_level))
    

    if args.verbose:
        print("\n[CONFIG] Parsed arguments:")
        print(f"  Query: {args.query}")
        print(f"  Port: {args.port}")
        print(f"  Model: {args.model}")
        print(f"  Temperature: {args.temperature}")
        print(f"  Max tokens: {args.max_tokens}")
        print(f"  Iterations: {args.iterations}")
        print(f"  Timeout: {args.timeout}")
        print(f"  Verbose: {args.verbose}")
        print(f"  Log level: {args.log_level}\n")
    
  
    result = asyncio.run(agentic(
        query=args.query,
        port=args.port,
        model=args.model,
        iterations=args.iterations,
        temp=args.temperature,
        max_tokens=args.max_tokens,
        verbose=args.verbose,
        timeout=args.timeout
    ))
    
    print("RESULTS:")
    print("="*70)
    print(f"Status: {result.get('status', 'unknown')}")
    print(f"Result:\n{result.get('result', result.get('query', result.get('message', 'N/A')))}")
    if result.get('iterations_used') is not None:
        print(f"Iterations used: {result['iterations_used']}")