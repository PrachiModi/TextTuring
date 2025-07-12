from PIL import Image
import os
import shutil
from pathlib import Path
import subprocess
import logging
import tempfile

logger = logging.getLogger(__name__)

MAX_PNG_SIZE = 1_048_576  # 1MB in bytes
MAX_DIMENSION = 1000      # Max width/height in pixels
MIN_DIMENSION = 100       # Minimum width/height
RESIZE_FACTORS = [0.9, 0.8, 0.7, 0.6, 0.5]  # Resize ratios

def scan_non_png_images(directory_path: str) -> list:
    """
    Scan directory for non-PNG images (JPEG/JPG) and PNGs that are actually JPEGs, skipping LegacyTextTuring, out, and temp folders.
    Returns: List of (file_path, relative_path, reason)
    """
    image_files = []
    skip_folders = {"legacytextturing", "out", "temp"}  # Case-insensitive set
    for root, _, files in os.walk(directory_path, topdown=True):
        if os.path.basename(root).lower() in skip_folders:
            continue
        try:
            for file in files:
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(root, directory_path).replace(os.sep, "/")
                if relative_path == ".":
                    relative_path = ""
                else:
                    relative_path += "/"
                reason = None
                if file.lower().endswith((".jpg", ".jpeg")):
                    reason = "JPEG"
                elif file.lower().endswith(".png"):
                    try:
                        with Image.open(file_path) as img:
                            if img.format in ("JPEG", "JPG"):
                                reason = "PNG is JPEG"
                    except Exception as e:
                        continue
                if reason:
                    image_files.append((file_path, relative_path, reason))
        except Exception as e:
            continue
    return image_files

def convert_to_png(file_path: str, parent_dir: str) -> tuple:
    """
    Convert a JPEG/JPG or misidentified PNG to proper PNG, ensuring size <1MB and dimensions ≤1000px.
    Copies original to temp, moves to LegacyTextTuring/Graphics after verifying PNG, skipping if exists.
    Returns: (new_file_path: str, error: str)
    """
    file_name = os.path.basename(file_path)
    temp_original = None
    try:
        if not os.path.exists(file_path):
            return None, "File not found"
        if not os.access(file_path, os.R_OK):
            return None, "No read permission"

        # Create LegacyTextTuring/Graphics folder
        legacy_folder = os.path.join(parent_dir, "LegacyTextTuring")
        graphics_folder = os.path.join(legacy_folder, "Graphics")
        log_file = os.path.join(legacy_folder, "Log.txt")
        os.makedirs(graphics_folder, exist_ok=True)
        dest_path = os.path.join(graphics_folder, file_name)

        # Check if backup already exists
        if os.path.exists(dest_path):
            os.remove(file_path)
            return None, "Backup already exists"

        # Copy original to temp location
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_name)[1]) as temp_file:
            temp_original = temp_file.name
            shutil.copy2(file_path, temp_original)

        # Load image
        try:
            img = Image.open(file_path)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.info.pop('icc_profile', None)
        except Exception as e:
            return None, f"Unidentified or unsupported image format: {str(e)}"

        # Resize to ensure dimensions ≤1000px while maintaining aspect ratio
        original_width, original_height = img.size
        if original_width > MAX_DIMENSION or original_height > MAX_DIMENSION:
            scale = min(MAX_DIMENSION / original_width, MAX_DIMENSION / original_height)
            new_width = int(original_width * scale)
            new_height = int(original_height * scale)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # New PNG path
        new_file_path = os.path.splitext(file_path)[0] + ".png"

        # Get relative path for logging
        directory_path = os.path.dirname(os.path.dirname(file_path))  # Parent of parent dir
        relative_path = os.path.relpath(os.path.dirname(file_path), directory_path).replace(os.sep, "/")
        if relative_path == ".":
            relative_path = ""
        else:
            relative_path += "/"

        # Try saving PNG with progressive resizing if needed
        for resize_factor in [1.0] + RESIZE_FACTORS:
            try:
                # Resize if not first attempt
                if resize_factor < 1.0:
                    new_width = int(original_width * resize_factor)
                    new_height = int(original_height * resize_factor)
                    if new_width < MIN_DIMENSION or new_height < MIN_DIMENSION:
                        break
                    img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                else:
                    img_resized = img

                # Save PNG
                img_resized.save(new_file_path, format='PNG', compress_level=9)

                # Optimize with oxipng if available
                try:
                    subprocess.run(["oxipng", "--opt", "max", "--strip", "all", new_file_path], check=True, capture_output=True)
                except (subprocess.CalledProcessError, FileNotFoundError):
                    pass

                # Verify PNG exists and is readable
                if not os.path.exists(new_file_path):
                    raise FileNotFoundError(f"PNG file missing: {new_file_path}")
                if not os.access(new_file_path, os.R_OK):
                    raise PermissionError(f"No read permission for PNG: {new_file_path}")

                # Check PNG size
                png_size = os.path.getsize(new_file_path)
                if png_size <= MAX_PNG_SIZE:
                    # Move temp original to LegacyTextTuring/Graphics
                    shutil.move(temp_original, dest_path)
                    # Remove original file only if it's different from new PNG path
                    if file_path != new_file_path and os.path.exists(file_path):
                        os.remove(file_path)
                    # Log conversion
                    log_path = relative_path + os.path.basename(new_file_path)
                    try:
                        with open(log_file, "a", encoding="utf-8") as f:
                            from check_image_sanity import CheckImageSanityWidget
                            if CheckImageSanityWidget.first_conversion:
                                f.write("--------------\nImages Converted\n")
                                CheckImageSanityWidget.first_conversion = False
                            f.write(f"{log_path} - converted to png\n")
                    except Exception as e:
                        logger.error(f"Error logging conversion for {file_path}: {str(e)}")
                    return new_file_path, None
                else:
                    os.remove(new_file_path)
            except Exception as e:
                if os.path.exists(new_file_path):
                    os.remove(new_file_path)
                continue

        # If all attempts fail, restore original
        if os.path.exists(file_path):
            pass
        else:
            shutil.move(temp_original, file_path)
        return None, "PNG size exceeds 1MB after resizing attempts"

    except Exception as e:
        # Restore original if it was copied
        if temp_original and os.path.exists(temp_original) and not os.path.exists(file_path):
            shutil.move(temp_original, file_path)
        return None, f"Unexpected error: {str(e)}"
    finally:
        # Clean up temp file if it exists
        if temp_original and os.path.exists(temp_original):
            os.remove(temp_original)

if __name__ == "__main__":
    exit(1)