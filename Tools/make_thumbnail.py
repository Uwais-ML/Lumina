# Tools/make_thumbnail.py
# name: make_thumbnail
# arguments: input_path, output_path, size. """Create a thumbnail. Requires Pillow (import name: PIL)."""
# description: Create a resized thumbnail of an image
# example: make_thumbnail(/path/in.jpg, /path/out.jpg, 128)
# returns: Success or error message

import sys

def main(input_path, output_path, size="128"):
    try:
        from PIL import Image

        img = Image.open(input_path)
        img.thumbnail((int(size), int(size)))
        img.save(output_path)
        print(f"Thumbnail saved: {output_path}")

    except ImportError as e:
        print(f"Error: {str(e)}")
    except FileNotFoundError:
        print(f"Error: File not found: {input_path}")
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) >= 4:
        main(sys.argv[1], sys.argv[2], sys.argv[3])
    else:
        print("Error: Usage: make_thumbnail <input> <output> <size>")