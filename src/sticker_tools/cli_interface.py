from .convert_optimize import convert_optimize
from .patch_duration import patch_duration
import os

def create_sticker():
    import sys
    # ensure at least one argument is provided
    if len(sys.argv) < 2:
        raise ValueError("No input file path provided. Usage: sticker <input_path>")
    input_path = sys.argv[1]
    # ensure the provided argument is a valid path
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")
    # determine extension
    ext = os.path.splitext(input_path)[1].lower()
    if ext == ".webm":
        # input is already WebM: only patch duration
        patch_duration(input_path)
    else:
        # convert other formats to WebM, then patch
        output_path = os.path.splitext(input_path)[0] + ".webm"
        convert_optimize(input_path)
        patch_duration(output_path)