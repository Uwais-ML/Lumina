# name: save_file
# arguments: location, content to save
# description: Write code or text to a file path on disk
# example: save_file("/path/to/file.txt", "print('hello world')")
# returns: Success or error message

import sys
import os
if len(sys.argv) >= 3:
    filepath = sys.argv[1]
    content = sys.argv[2] if len(sys.argv) == 3 else ", ".join(sys.argv[2:])
    
    # Normalize leading slash if model omitted it for Users/...
    if filepath.startswith("Users/"):
        filepath = "/" + filepath
    
    # Remove quotes
    if content.startswith('"') and content.endswith('"'):
        content = content[1:-1]
    
    # Create directory
    directory = os.path.dirname(filepath)
    if directory:
        os.makedirs(directory, exist_ok=True)
    
    # Write file
    with open(filepath, "w") as f:
        f.write(content)
    
    print(f"Success: File saved to {filepath}")
else:
    print("Error: Need filepath and content")
