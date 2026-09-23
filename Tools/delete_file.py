# Tools/delete_file.py
# name: delete_file
# arguments: filepath
# description: Delete a file from disk
# example: delete_file(/path/to/file.txt)
# returns: Success or error message

import sys
import os

def main(filepath):
    """Delete file."""
    try:
        if not os.path.exists(filepath):
            print(f"Error: File not found")
            return
        
        os.remove(filepath)
        print(f"File deleted: {filepath}")
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) >= 2:
        main(sys.argv[1])