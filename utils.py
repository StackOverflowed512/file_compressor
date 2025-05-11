# universal_file_compressor/utils.py
import os
from typing import Tuple

def get_formatted_size(size_bytes: int) -> str:
    """Converts bytes to a human-readable string (B, KB, MB, GB)."""
    if size_bytes < 0: # Should not happen for file sizes
        return "Invalid Size"
    if size_bytes == 0:
        return "0 B"
    size_name: Tuple[str, ...] = ("B", "KB", "MB", "GB", "TB")
    i = 0
    # Ensure size_bytes is float for division
    size_bytes_float = float(size_bytes)
    while size_bytes_float >= 1024 and i < len(size_name) - 1:
        size_bytes_float /= 1024.0
        i += 1
    return f"{size_bytes_float:.2f} {size_name[i]}"

def create_output_folder(folder_name: str = "compressed") -> str:
    """Creates the output folder if it doesn't exist."""
    if not os.path.exists(folder_name):
        try:
            os.makedirs(folder_name)
        except OSError as e:
            print(f"Error creating directory {folder_name}: {e}")
            # Fallback or raise, depending on desired strictness
            raise
    return folder_name

OUTPUT_FOLDER = create_output_folder() # Ensure it's created at import time