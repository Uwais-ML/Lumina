import sys
import os
import subprocess
import re

def execute_tool(tool_call: str):
    """Execute tool directly."""
    try:
        print(f"[1] Input: {tool_call}")
        
        match = re.match(r'(\w+)\((.*)\)', tool_call.strip())
        if not match:
            return f"Error: Invalid format"
        
        tool_name, args_str = match.groups()
        print(f"[2] Tool name: {tool_name}")
        print(f"[3] Args string: {args_str}")
        
        args = []
        for arg in args_str.split(','):
            arg = arg.strip()
            if (arg.startswith('"') and arg.endswith('"')) or (arg.startswith("'") and arg.endswith("'")):
                arg = arg[1:-1]
            args.append(arg)
        
        print(f"[4] Parsed args: {args}")
        
        tool_file = os.path.join("Tools", f"{tool_name}.py")
        print(f"[5] Tool file: {tool_file}")
        print(f"[6] Exists? {os.path.exists(tool_file)}")
        
        if not os.path.exists(tool_file):
            return f"Error: Tool not found at {tool_file}"
        
        cmd = [sys.executable, tool_file] + args
        print(f"[7] Command: {cmd}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        print(f"[8] Return code: {result.returncode}")
        print(f"[9] Stdout: {result.stdout}")
        print(f"[10] Stderr: {result.stderr}")
        
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            return f"Error: {result.stderr.strip()}"
    
    except Exception as e:
        return f"Error: {str(e)}"


if __name__ == "__main__":
    tool_call = 'save_file("/Users/apple/Lumina/logs/test.txt","PyTorch")'
    result = execute_tool(tool_call)
    print(f"\nFinal Result: {result}")