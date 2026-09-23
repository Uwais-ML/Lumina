# Tools/peek_code.py
# name: peek_code
# arguments: filepath, start_line
# description: Read a Python file in a sliding window of 30 lines. Returns the requested slice plus the arguments needed to fetch the next window. 
# example: peek_code(/path/to/file.py, 1)
# returns: Window of code (30 lines), total line count, and the args for the next call

import sys
import os

WINDOW = 30

def main(filepath, start_line="1"):
    """Return a 30-line window of a file, plus next-call args."""
    try:
        if not os.path.exists(filepath):
            print(f"Error: File not found: {filepath}")
            return

        if not os.path.isfile(filepath):
            print(f"Error: Not a file: {filepath}")
            return

        try:
            start = max(1, int(start_line))
        except ValueError:
            print(f"Error: start_line must be an integer, got '{start_line}'")
            return

        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total = len(lines)
        if total == 0:
            print(f"File: {filepath} (empty)")
            return

        if start > total:
            print(f"Error: start_line {start} is past end of file (total {total} lines)")
            return

        end = min(start + WINDOW - 1, total)
        window = lines[start - 1:end]

        # Print header
        print(f"File: {filepath}")
        print(f"Total lines: {total}")
        print(f"Showing lines {start}-{end} of {total}")
        print("-" * 60)

        # Print with line numbers
        width = len(str(end))
        for i, line in enumerate(window, start=start):
            print(f"{i:>{width}} | {line.rstrip()}")

        print("-" * 60)

        # Tell the agent what to do next
        if end < total:
            next_start = end + 1
            print(f"NEXT WINDOW: peek_code({filepath}, {next_start})")
            print(f"Remaining lines after this window: {total - end}")
        else:
            print("END OF FILE — no more lines.")

    except UnicodeDecodeError as e:
        print(f"Error: Could not decode file as text: {str(e)}")
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) >= 2:
        start = sys.argv[2] if len(sys.argv) >= 3 else "1"
        main(sys.argv[1], start)
    else:
        print("Error: Usage: peek_code <filepath> [start_line]")