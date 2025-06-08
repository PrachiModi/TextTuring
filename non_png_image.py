import os
import logging
import shutil
from PIL import Image
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_PNG_SIZE = 1_048_576  # 1MB in bytes
MIN_DIMENSION = 100       # Minimum width/height
RESIZE_FACTORS = [0.9, 0.8, 0.7, 0.6, 0.5]  # Resize ratios

def scan_non_png_images(directory_path: str) -> list:
    """
    Scan directory for non-PNG images (JPEG/JPG).
    Returns: List of (file_path, relative_path, reason)
    """
    image_files = []
    for root, dirs, files in os.walk(directory_path, topdown=True):
        try:
            for file in files:
                if file.lower().endswith((".jpg", ".jpeg")):
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(root, directory_path).replace(os.sep, "/")
                    if relative_path == ".":
                        relative_path = ""
                    else:
                        relative_path += "/"
                    reason = "JPEG"
                    image_files.append((file_path, relative_path, reason))
        except Exception as e:
            logger.error(f"Error scanning directory {root}: {str(e)}")
            continue
    logger.debug(f"Found {len(image_files)} non-PNG images")
    return image_files

def convert_to_png(file_path: str, parent_dir: str) -> tuple:
    """
    Convert a JPEG/JPG to PNG, aiming for small size (~9KB) and optionally resizing to <1MB.
    Moves original to LegacyTextTuring.
    Returns: (new_file_path: str, error: str)
    """
    try:
        file_name = os.path.basename(file_path)
        logger.debug(f"Converting {file_path} to PNG")
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return None, "File not found"
        if not os.access(file_path, os.R_OK):
            logger.error(f"No read permission for {file_path}")
            return None, "No read permission"

        # Create LegacyTextTuring folder
        legacy_folder = os.path.join(parent_dir, "LegacyTextTuring")
        os.makedirs(legacy_folder, exist_ok=True)
        dest_path = os.path.join(legacy_folder, file_name)
        if os.path.exists(dest_path):
            logger.error(f"File already exists in LegacyTextTuring: {dest_path}")
            return None, f"File already exists in LegacyTextTuring: {file_name}"

        # Move original to LegacyTextTuring
        shutil.move(file_path, dest_path)
        logger.debug(f"Moved {file_path} to {dest_path}")

        # Load image once
        try:
            img = Image.open(dest_path)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            # Strip ICC profile to avoid libpng warnings
            img.info.pop('icc_profile', None)
        except Exception as e:
            logger.error(f"Failed to open {dest_path}: {str(e)}")
            shutil.move(dest_path, file_path)  # Restore original
            return None, f"Unidentified or unsupported image format: {str(e)}"

        # Initial dimensions
        original_width, original_height = img.size
        logger.debug(f"Original dimensions: {original_width}x{original_height}")

        # New PNG path
        new_file_path = os.path.splitext(file_path)[0] + ".png"

        # Try saving PNG with progressive resizing
        for resize_factor in [1.0] + RESIZE_FACTORS:
            try:
                # Resize if not first attempt
                if resize_factor < 1.0:
                    new_width = int(original_width * resize_factor)
                    new_height = int(original_height * resize_factor)
                    if new_width < MIN_DIMENSION or new_height < MIN_DIMENSION:
                        logger.warning(f"Resize aborted for {file_name}: Dimensions {new_width}x{new_height} below minimum {MIN_DIMENSION}")
                        break
                    img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    logger.debug(f"Resized {file_name} to {new_width}x{new_height} (factor: {resize_factor})")
                else:
                    img_resized = img

                # Save PNG
                img_resized.save(new_file_path, format='PNG', compress_level=9, optimize=True)
                logger.debug(f"Saved PNG to {new_file_path}")

                # Optimize with oxipng if available
                try:
                    subprocess.run(["oxipng", "--opt", "max", "--strip", "all", new_file_path], check=True, capture_output=True)
                    logger.debug(f"Optimized {new_file_path} with oxipng")
                except (subprocess.CalledProcessError, FileNotFoundError) as e:
                    logger.warning(f"oxipng optimization failed for {new_file_path}: {str(e)}")

                # Check PNG size
                png_size = os.path.getsize(new_file_path)
                logger.debug(f"PNG size: {png_size} bytes")
                if png_size <= MAX_PNG_SIZE:
                    logger.debug(f"Conversion successful: {new_file_path}, size: {png_size} bytes")
                    return new_file_path, None
                else:
                    logger.debug(f"PNG size {png_size} exceeds 1MB, trying next resize factor")
                    os.remove(new_file_path)  # Delete oversized PNG
            except Exception as e:
                logger.error(f"Error saving PNG for {file_name}: {str(e)}")
                if os.path.exists(new_file_path):
                    os.remove(new_file_path)
                continue

        # If all attempts fail, restore original
        logger.error(f"Failed to create PNG under 1MB for {file_name}")
        shutil.move(dest_path, file_path)
        return None, "PNG size exceeds 1MB after resizing attempts"

    except Exception as e:
        logger.error(f"Unexpected error converting {file_path}: {str(e)}")
        if os.path.exists(dest_path) and not os.path.exists(file_path):
            shutil.move(dest_path, file_path)
        return None, f"Unexpected error: {str(e)}"

if __name__ == "__main__":
    logger.error("This module is not meant to be run directly. Import it in your main application.")
    exit(1)