# Tools/color_print.py
# name: color_print
# arguments: text, color
# description: Print text to the terminal in a chosen color
# example: color_print(hello world, red)
# returns: Colored text printed to stdout

import sys

def main(text, color="white"):
    """Print colored text using colorama (requires colorama installed)."""
    try:
        from colorama import Fore, Style, init
        init(autoreset=True)

        colors = {
            "red": Fore.RED,
            "green": Fore.GREEN,
            "yellow": Fore.YELLOW,
            "blue": Fore.BLUE,
            "magenta": Fore.MAGENTA,
            "cyan": Fore.CYAN,
            "white": Fore.WHITE,
        }

        if color.lower() not in colors:
            print(f"Error: Unknown color '{color}'. Options: {', '.join(colors)}")
            return

        print(f"{colors[color.lower()]}{text}{Style.RESET_ALL}")

    except ImportError:
        print("Error: 'colorama' is not installed. Install it with: pip install colorama")
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) >= 2:
        color = sys.argv[2] if len(sys.argv) >= 3 else "white"
        main(sys.argv[1], color)
    else:
        print("Error: No text provided")