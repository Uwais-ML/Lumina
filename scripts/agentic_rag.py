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


def get_all_tools():
    """Returns headers of all available tools."""
    tools = ""
    abs_folder = os.path.abspath(folder_path)
    if os.path.exists(abs_folder):
        for filename in sorted(os.listdir(abs_folder)):
            filepath = os.path.join(abs_folder, filename)
            if os.path.isfile(filepath) and filename.endswith('.py'):
                with open(filepath, "r", encoding="utf-8", errors="ignore") as file:
                    for _ in range(6):
                        line = file.readline()
                        tools += line
                        if not line:
                            break
    return tools if tools else None


def classifyiftoolsneeded(query, timeout=60):
    """Classify if tools needed. Falls back to all tools if classifier is unreachable."""
    try:
        port = classifier.initialize()
        
        if classifier.Model_status and port is not None:
            import Smartswitch
            payload = {
                "model": "qwen",
                "temperature": 0,
                "max_tokens": 50,
                "messages": [
                    {
                        "role": "system",
                        "content": "Answer only: tools or not_tools"
                    },
                    {
                        "role": "user",
                        "content": f"{query}"
                    }
                ]
            }
            response = Smartswitch.safe_query(port, payload=payload, timeout=timeout)
            if response is not None and response.status_code == 200:
                decision = response.json()["choices"][0]["message"]["content"].strip().lower()
                if "not_tools" in decision or "not tools" in decision:
                    return None
    except Exception as e:
        logging.warning(f"Classification skipped or failed ({e}); falling back to all available tools.")
    
    return get_all_tools()


def execute_tool(tool_call: str):
    """Execute tool directly."""
    try:
        print(f"\n[EXEC] Input: {tool_call}")
        
        match = re.match(r'(\w+)\((.*)\)', tool_call.strip())
        if not match:
            return "Error: Invalid format. Use: toolname(arg1,arg2)"
        
        tool_name, args_str = match.groups()
        print(f"[EXEC] Tool: {tool_name}, Args: {args_str}")
        
        # Parse arguments cleanly handling commas inside quotes
        import csv
        try:
            parsed = next(csv.reader([args_str], skipinitialspace=True))
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
        print(f"[EXEC] Looking for: {tool_file}")
        
        if not os.path.exists(tool_file):
            return f"Error: Tool not found at {tool_file}"

        # Execute using the bundled CPython (cross-platform)
        python_bin = get_bundled_python()
        print(f"[EXEC] Python: {python_bin}")
        cmd = [python_bin, tool_file] + args
        print(f"[EXEC] Running: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        print(f"[EXEC] Return code: {result.returncode}")
        print(f"[EXEC] Stdout: {result.stdout}")
        if result.stderr:
            print(f"[EXEC] Stderr: {result.stderr}")
        
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            return f"Error: {result.stderr.strip()}"
    
    except subprocess.TimeoutExpired:
        return "Error: Tool execution timeout"
    except Exception as e:
        return f"Error: {str(e)}"


async def agentic(query, port, iterations=5, temp=0.1, max_tokens=256, verbose=False, timeout=120):
    """Main agentic loop."""
    if verbose:
        print(f"\n[AGENTIC] Starting with query: {query}")
        print(f"[AGENTIC] Port: {port}, Iterations: {iterations}")
    
    Tools = classifyiftoolsneeded(query, timeout=min(timeout, 60))
    
    if not Tools:
        return {"status": "no_tools_needed", "query": query}
    
    if verbose:
        print(f"[AGENTIC] Tools found:\n{Tools}\n")
    
    prompt = f"Query: {query}\n\nAvailable Tools:\n{Tools}"
    whatsdone = ""
    
    while iterations > 0:
        try:
            if verbose:
                print(f"\n[LOOP] Iteration {5 - iterations + 1}")
            
            import Smartswitch
            payload = {
                "model": "qwen",
                "temperature": temp,
                "max_tokens": max_tokens,
                "messages": [
                    {
                        "role": "system",
                        "content": """Output ONLY tool calls. Format: toolname(arg1,arg2)
Select the best tool from Available Tools to satisfy the query.
When the required task is done, output DONE."""
                    },
                    {
                        "role": "user",
                        "content": f"{prompt}\n\nPreviously executed:{whatsdone}"
                    }
                ]
            }
            response = Smartswitch.safe_query(port, payload=payload, timeout=timeout)
            if response is None or response.status_code != 200:
                print(f"[!] Warning: Query failed or timed out during agent loop.")
                break
            
            full_response = response.json()["choices"][0]["message"]["content"].strip()
            if verbose:
                print(f"[LLM] Response:\n{full_response}")
            
            lines = full_response.split('\n')
            executed_any = False
            
            # Extract tool calls from standard toolname(...) or tool:/argument: format
            tool_calls = []
            curr_tool = None
            curr_arg = None
            
            for line in lines:
                sline = line.strip()
                if not sline:
                    continue
                match = re.search(r'(\b\w+)\((.*)\)', sline)
                if match and not sline.lower().startswith("example:"):
                    tool_calls.append(f"{match.group(1)}({match.group(2)})")
                elif sline.lower().startswith("tool:"):
                    curr_tool = sline.split(":", 1)[1].strip()
                elif sline.lower().startswith("argument:") or sline.lower().startswith("arguments:"):
                    curr_arg = sline.split(":", 1)[1].strip()
                    if curr_tool and curr_arg:
                        tool_calls.append(f"{curr_tool}({curr_arg})")
                        curr_tool = None
                        curr_arg = None
                elif verbose and not re.match(r'^\w+\(.*\)$', sline):
                    print(f"[SKIP] Not a tool call: {sline}")

            for tool_call in tool_calls:
                if verbose:
                    print(f"[LLM] Decision: {tool_call}")
                
                # Execute tool
                tool_result = execute_tool(tool_call)
                if verbose:
                    print(f"[RESULT] {tool_result}")
                
                whatsdone += f"\n→ {tool_call}\n← {tool_result}"
                executed_any = True
            
            # Check if we're done
            if "DONE" in full_response.upper() or (executed_any and ("Success" in whatsdone or "Written:" in whatsdone)):
                if verbose:
                    print(f"[AGENTIC] Task complete!")
                return {
                    "status": "success",
                    "result": whatsdone,
                    "iterations_used": 5 - iterations + 1
                }
            
            iterations -= 1
            
        except Exception as e:
            print(f"[ERROR] {e}")
            logging.error(f"Agentic loop error: {e}")
            return {
                "status": "error",
                "message": str(e),
                "partial_result": whatsdone
            }
    
    return {
        "status": "incomplete",
        "message": "Max iterations reached",
        "result": whatsdone,
        "iterations_used": 5
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