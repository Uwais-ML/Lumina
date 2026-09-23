# Tools/code_and_run.py
# name: code_and_run
# arguments: filename, code
# description: Write Python code to a file and execute it, returning the output
# example: code_and_run(sort.py, import random; print(sorted([3,1,2])))
# returns: Path of the saved script, plus stdout/stderr from execution

import sys
import os
import subprocess

TOOLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "generated")

def main(filename, code):
    """Write code to a file and run it in a subprocess."""
    try:
        # Sanitize filename — no path traversal, must end in .py
        filename = os.path.basename(filename)
        if not filename.endswith(".py"):
            filename += ".py"

        os.makedirs(TOOLS_DIR, exist_ok=True)
        script_path = os.path.join(TOOLS_DIR, filename)

        # Write the code
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code)

        print(f"Written: {script_path}")

        # Run it in a subprocess with a timeout
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=TOOLS_DIR,
        )

        if result.stdout:
            print("Output:")
            print(result.stdout, end="")

        if result.stderr:
            print("Stderr:")
            print(result.stderr, end="")

        if result.returncode != 0:
            print(f"Process exited with code {result.returncode}")
        elif not result.stdout and not result.stderr:
            print("Ran successfully (no output)")

    except subprocess.TimeoutExpired:
        print("Error: Script timed out after 30 seconds")
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        main(sys.argv[1], sys.argv[2])
    else:
        print("Error: Usage: code_and_run <filename> <code>")