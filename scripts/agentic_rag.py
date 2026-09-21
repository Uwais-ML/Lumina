import logging
import classifier
import requests
import os
import platform
import subprocess
import re
import sys
import asyncio
import argparse

os.makedirs("Tools", exist_ok=True)
folder_path = "Tools"

logging.basicConfig(level=logging.INFO)

# ── Bundled Python resolver (mirrors Lumina.py cross-platform detection) ──────
_SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)


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
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    
    return parser  # ← IMPORTANT: Return the parser!


def classifyiftoolsneeded(query):
    """Classify if tools needed."""
    port = classifier.initialize()
    
    if classifier.Model_status and port is not None:
        try:
            response = requests.post(
                f"http://127.0.0.1:{port}/v1/chat/completions",
                json={
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
                },
                timeout=15
            )
            
            decision = response.json()["choices"][0]["message"]["content"].strip().lower()
            
            if "not_tools" in decision or "not tools" in decision:
                return None
            
            tools = ""
            abs_folder = os.path.abspath(folder_path)
            
            for filename in os.listdir(abs_folder):
                filepath = os.path.join(abs_folder, filename)
                if os.path.isfile(filepath) and filename.endswith('.py'):
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as file:
                        for _ in range(6):
                            line = file.readline()
                            tools += line
                            if not line:
                                break
            
            return tools if tools else None
            
        except Exception as e:
            logging.error(f"Classification error: {e}")
            return None
    
    return None


def execute_tool(tool_call: str):
    """Execute tool directly."""
    try:
        print(f"\n[EXEC] Input: {tool_call}")
        
        match = re.match(r'(\w+)\((.*)\)', tool_call.strip())
        if not match:
            return "Error: Invalid format. Use: toolname(arg1,arg2)"
        
        tool_name, args_str = match.groups()
        print(f"[EXEC] Tool: {tool_name}, Args: {args_str}")
        
        # Parse arguments
        args = []
        for arg in args_str.split(','):
            arg = arg.strip()
            # Remove all types of quotes
            if arg.startswith('"') and arg.endswith('"'):
                arg = arg[1:-1]
            elif arg.startswith("'") and arg.endswith("'"):
                arg = arg[1:-1]
            args.append(arg)
        
        print(f"[EXEC] Parsed args: {args}")
        
        # Find tool file
        tool_file = os.path.join("Tools", f"{tool_name}.py")
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


async def agentic(query, port, iterations=5, temp=0.1, max_tokens=256, verbose=False):
    """Main agentic loop."""
    if verbose:
        print(f"\n[AGENTIC] Starting with query: {query}")
        print(f"[AGENTIC] Port: {port}, Iterations: {iterations}")
    
    Tools = classifyiftoolsneeded(query)
    
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
            
            response = requests.post(
                f"http://127.0.0.1:{port}/v1/chat/completions",
                json={
                    "model": "qwen",
                    "temperature": temp,
                    "max_tokens": max_tokens,
                    "messages": [
                        {
                            "role": "system",
                            "content": """Output ONLY tool calls. Format: toolname(arg1,arg2)
You only call Tool nothing else based on the query
When all tasks done: DONE."""
                        },
                        {
                            "role": "user",
                            "content": f"{prompt}\n\nPreviously executed:{whatsdone}"
                        }
                    ]
                },
                timeout=40
            )
            
            full_response = response.json()["choices"][0]["message"]["content"].strip()
            if verbose:
                print(f"[LLM] Response:\n{full_response}")
            
            lines = full_response.split('\n')
            executed_any = False
            
            for line in lines:
                line = line.strip()
                
                # Skip empty lines, DONE, imports, assignments
                if not line or "DONE" in line.upper():
                    continue
                
                # Only accept lines that match: toolname(...)
                if not re.match(r'^\w+\(.*\)$', line):
                    if verbose:
                        print(f"[SKIP] Not a tool call: {line}")
                    continue
                
                if verbose:
                    print(f"[LLM] Decision: {line}")
                
                # Execute tool
                tool_result = execute_tool(line)
                if verbose:
                    print(f"[RESULT] {tool_result}")
                
                whatsdone += f"\n→ {line}\n← {tool_result}"
                executed_any = True
            
            # Check if we're done
            if "DONE" in full_response.upper():
                if verbose:
                    print(f"[AGENTIC] Task complete!")
                return {
                    "status": "success",
                    "result": whatsdone,
                    "iterations_used": 5 - iterations
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
        print(f"  Verbose: {args.verbose}")
        print(f"  Log level: {args.log_level}\n")
    
  
    result = asyncio.run(agentic(
        query=args.query,
        port=args.port,
        iterations=args.iterations,
        temp=args.temperature,
        max_tokens=args.max_tokens,
        verbose=args.verbose
    ))
    
    print("RESULTS:")
    print("="*70)
    print(f"Status: {result['status']}")
    print(f"Result:\n{result['result']}")
    if 'iterations_used' in result:
        print(f"Iterations used: {result['iterations_used']}")