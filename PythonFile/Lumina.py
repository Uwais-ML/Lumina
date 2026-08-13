# Lumina.py
import sys

def main():
    if len(sys.argv) < 2:
        print("Usage: python script.py <your_input>")
        print("Example: python script.py hello")
        sys.exit(1)
    
    user_input = sys.argv[1]
    print(f"You said: {user_input}")
    
    print(f"Processing: {user_input.upper()}")

if __name__ == "__main__":
    main()