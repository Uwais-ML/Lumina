# Tools/pip_install.py
# name: pip_install
# arguments: package
# description: Install a Python library using pip
# example: pip_install(requests)
# returns: Success or error message

import sys
import subprocess

def main(package):
    """Install a Python package via pip."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print(f"Successfully installed: {package}")
            if result.stdout.strip():
                print(result.stdout.strip())
        else:
            print(f"Error installing {package}:")
            print(result.stderr.strip() if result.stderr else "Unknown error")
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) >= 2:
        main(sys.argv[1])
    else:
        print("Error: No package specified")