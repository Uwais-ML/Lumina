# Tools/read_file.py
# name: read_file
# arguments: filepath
# description: Reads content from a file
# example: read_file(/path/to/file.txt)
# returns: File content

import sys
import os

def main(filepath):
    """Read file content."""
    try:
        if not os.path.exists(filepath):
            print(f"Error: File not found at {filepath}")
            return
        
        with open(filepath, "r") as f:
            content = f.read()
        
        print(content)
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) >= 2:
        main(sys.argv[1])
    else:
        print("Error: Missing filepath")