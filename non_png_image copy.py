from PIL import Image
import os
import shutil
from pathlib import Path
import subprocess
import io
import logging
import tempfile

logger = logging.getLogger(__name__)

MAX_PNG_SIZE = 1_048_576  # 1MB in bytes
MIN_DIMENSION = 100       # Minimum width/height
MAX_DIMENSION = 999      # Maximum width/height
RESIZE_FACTORS = [0.9, 0.8, 0.7, 0.6, 0.5]  # Resize ratios

def scan_non_png_images(directory_path: str) -> list:
    """
    Scan directory for non-PNG images (JPEG/JPG) and PNGs that are actually JPEGs, skipping LegacyTextTuring, out, and temp folders.
    Returns: List of (file_path, relative_path, reason)
    """
    image_files = []
    skip_folders = {"legacytextturing", "out", "temp"}
    for root, _, files in os.walk(directory_path, topdown=True):
        if os.path.basename(root).lower() in skip_folders:
            continue
        try:
            for file in files:
                file_path = os.path.join(root, file)
                file_name = os.path.basename(file_path)
                relative_path = os.path.relpath(root, directory_path).replace(os.sep, "/")
                if relative_path == ".":
                    relative_path = ""
                else:
                    relative_path += "/"
                reason = None
                if file.lower().endswith((".jpg", ".jpeg")):
                    reason = "JPEG"
                    if file_name.lower().startswith("illus_517_c"):
                        print(f"[Illus_517_C Debug] Found JPEG: {file_path}")
                elif file.lower().endswith(".png"):
                    try:
                        with Image.open(file_path) as img:
                            if img.format in ("JPEG", "JPG"):
                                reason = "PNG is JPEG"
                                if file_name.lower().startswith("illus_517_c"):
                                    print(f"[Illus_517_C Debug] Found PNG with JPEG content: {file_path}, Format: {img.format}, Size: {img.size}")
                    except Exception as e:
                        if file_name.lower().startswith("illus_517_c"):
                            print(f"[Illus_517_C Debug] Failed to open {file_path}: {str(e)}")
                        continue
                if reason:
                    image_files.append((file_path, relative_path, reason))
                    if file_name.lower().startswith("illus_517_c"):
                        print(f"[Illus_517_C Debug] Added to list: {file_path} (Reason: {reason})")
        except Exception as e:
            if any(file.lower().startswith("illus_517_c") for file in files):
                print(f"[Illus_517_C Debug] Error scanning directory {root}: {str(e)}")
            continue
    return image_files

def convert_to_png(file_path: str, parent_dir: str) -> tuple:
    """
    Convert a JPEG/JPG or misidentified PNG to proper PNG, ensuring size ≤1MB and width/height ≤999 pixels.
    Copies original to temp, moves to LegacyTextTuring/Graphics only after verifying PNG, skipping if exists.
    Returns: (new_file_path: str, error: str)
    """
    file_name = os.path.basename(file_path)
    is_target_file = file_name.lower().startswith("illus_517_c")
    if is_target_file:
        print(f"[Illus_517_C Debug] Starting conversion for: {file_path}")
    temp_original = None
    try:
        if not os.path.exists(file_path):
            if is_target_file:
                print(f"[Illus_517_C Debug] File does not exist: {file_path}")
            return None, "File not found"
        if not os.access(file_path, os.R_OK):
            if is_target_file:
                print(f"[Illus_517_C Debug] No read permission for: {file_path}")
            return None, "No read permission"

        # Create LegacyTextTuring/Graphics folder
        legacy_folder = os.path.join(parent_dir, "LegacyTextTuring")
        graphics_folder = os.path.join(legacy_folder, "Graphics")
        log_file = os.path.join(legacy_folder, "Log.txt")
        if is_target_file:
            print(f"[Illus_517_C Debug] Creating backup folder: {graphics_folder}")
        os.makedirs(graphics_folder, exist_ok=True)
        dest_path = os.path.join(graphics_folder, file_name)
        if is_target_file:
            print(f"[Illus_517_C Debug] Backup destination: {dest_path}")

        # Check if backup already exists
        if os.path.exists(dest_path):
            if is_target_file:
                print(f"[Illus_517_C Debug] Backup already exists at {dest_path}. Removing original.")
            os.remove(file_path)
            return None, "Backup already exists"

        # Copy original to temp location
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_name)[1]) as temp_file:
            temp_original = temp_file.name
            if is_target_file:
                print(f"[Illus_517_C Debug] Copying original to temp: {temp_original}")
            shutil.copy2(file_path, temp_original)

        # Load image
        try:
            if is_target_file:
                print(f"[Illus_517_C Debug] Loading image: {file_path}")
            img = Image.open(file_path)
            if img.mode != 'RGB':
                if is_target_file:
                    print(f"[Illus_517_C Debug] Converting image mode to RGB from {img.mode}")
                img = img.convert('RGB')
            img.info.pop('icc_profile', None)
            if is_target_file:
                print(f"[Illus_517_C Debug] Image loaded successfully. Size: {img.size}")
        except Exception as e:
            if is_target_file:
                print(f"[Illus_517_C Debug] Failed to load image {file_path}: {str(e)}")
            return None, f"Unidentified or unsupported image format: {str(e)}"

        # Initial dimensions
        original_width, original_height = img.size
        if is_target_file:
            print(f"[Illus_517_C Debug] Original dimensions: {original_width}x{original_height}")

        # New PNG path
        new_file_path = os.path.splitext(file_path)[0] + ".png"
        if is_target_file:
            print(f"[Illus_517_C Debug] New PNG path: {new_file_path}")

        # Calculate initial resize factor to ensure width and height ≤ 999 pixels
        max_current_dimension = max(original_width, original_height)
        if max_current_dimension > MAX_DIMENSION:
            initial_resize_factor = MAX_DIMENSION / max_current_dimension
            if is_target_file:
                print(f"[Illus_517_C Debug] Initial resize factor to meet 999px limit: {initial_resize_factor}")
        else:
            initial_resize_factor = 1.0
            if is_target_file:
                print(f"[Illus_517_C Debug] No initial resize needed for dimensions")

        # Combine resize factors
        resize_factors = [initial_resize_factor] if initial_resize_factor < 1.0 else [1.0]
        resize_factors.extend([f for f in RESIZE_FACTORS if f < initial_resize_factor])

        # Try saving PNG with progressive resizing
        for resize_factor in resize_factors:
            try:
                if is_target_file:
                    print(f"[Illus_517_C Debug] Attempting resize factor: {resize_factor}")
                # Resize if not first attempt or required for dimensions
                if resize_factor < 1.0:
                    new_width = int(original_width * resize_factor)
                    new_height = int(original_height * resize_factor)
                    if new_width < MIN_DIMENSION or new_height < MIN_DIMENSION:
                        if is_target_file:
                            print(f"[Illus_517_C Debug] Dimensions too small: {new_width}x{new_height}. Stopping resize.")
                        break
                    if is_target_file:
                        print(f"[Illus_517_C Debug] Resizing to: {new_width}x{new_height}")
                    img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                else:
                    img_resized = img

                # Save PNG
                if is_target_file:
                    print(f"[Illus_517_C Debug] Saving PNG to: {new_file_path}")
                img_resized.save(new_file_path, format='PNG', compress_level=9)
                if is_target_file:
                    print(f"[Illus_517_C Debug] PNG saved successfully.")

                # Optimize with oxipng if available
                try:
                    if is_target_file:
                        print(f"[Illus_517_C Debug] Optimizing PNG with oxipng: {new_file_path}")
                    subprocess.run(["oxipng", "--opt", "max", "--strip", "all", new_file_path], check=True, capture_output=True)
                    if is_target_file:
                        print(f"[Illus_517_C Debug] Oxipng optimization completed.")
                except (subprocess.CalledProcessError, FileNotFoundError) as e:
                    if is_target_file:
                        print(f"[Illus_517_C Debug] Oxipng failed or not found: {str(e)}")

                # Verify PNG exists and is readable
                if not os.path.exists(new_file_path):
                    if is_target_file:
                        print(f"[Illus_517_C Debug] PNG not found after saving: {new_file_path}")
                    raise FileNotFoundError(f"PNG file missing: {new_file_path}")
                if not os.access(new_file_path, os.R_OK):
                    if is_target_file:
                        print(f"[Illus_517_C Debug] No read permission for PNG: {new_file_path}")
                    raise PermissionError(f"No read permission for PNG: {new_file_path}")

                # Check PNG size
                png_size = os.path.getsize(new_file_path)
                if is_target_file:
                    print(f"[Illus_517_C Debug] PNG size: {png_size} bytes ({png_size / (1024 * 1024):.2f} MB)")
                if png_size <= MAX_PNG_SIZE:
                    # Move temp original to LegacyTextTuring/Graphics
                    if is_target_file:
                        print(f"[Illus_517_C Debug] Moving temp original to: {dest_path}")
                    shutil.move(temp_original, dest_path)
                    if is_target_file:
                        print(f"[Illus_517_C Debug] Original moved successfully.")
                    # Remove original file only if it's different from new PNG path
                    if file_path != new_file_path and os.path.exists(file_path):
                        if is_target_file:
                            print(f"[Illus_517_C Debug] Removing original: {file_path}")
                        os.remove(file_path)
                    # Log conversion
                    log_path = "Accessing CloudVision Appliance/" + file_name
                    try:
                        if is_target_file:
                            print(f"[Illus_517_C Debug] Logging conversion to: {log_file}")
                        with open(log_file, "a", encoding="utf-8") as f:
                            from check_image_sanity import CheckImageSanityWidget
                            if CheckImageSanityWidget.first_conversion:
                                f.write("--------------\nImages Converted\n")
                                CheckImageSanityWidget.first_conversion = False
                            f.write(f"{log_path} - converted to png\n")
                        if is_target_file:
                            print(f"[Illus_517_C Debug] Conversion logged successfully.")
                    except Exception as e:
                        if is_target_file:
                            print(f"[Illus_517_C Debug] Error logging conversion for {file_path}: {str(e)}")
                        logger.error(f"Error logging conversion for {file_path}: {str(e)}")
                    if is_target_file:
                        print(f"[Illus_517_C Debug] Conversion successful for: {new_file_path}")
                    return new_file_path, None
                else:
                    if is_target_file:
                        print(f"[Illus_517_C Debug] PNG size exceeds limit: {png_size} bytes. Deleting: {new_file_path}")
                    os.remove(new_file_path)
            except Exception as e:
                if os.path.exists(new_file_path):
                    if is_target_file:
                        print(f"[Illus_517_C Debug] Error during processing. Deleting: {new_file_path}")
                    os.remove(new_file_path)
                if is_target_file:
                    print(f"[Illus_517_C Debug] Error processing {file_path} at resize factor {resize_factor}: {str(e)}")
                logger.error(f"Error processing {file_path} at resize_factor {resize_factor}: {str(e)}")
                continue

        # If all attempts fail, restore original
        if is_target_file:
            print(f"[Illus_517_C Debug] Conversion failed for {file_path}: PNG size exceeds 1MB or dimensions not met")
        if os.path.exists(file_path):
            if is_target_file:
                print(f"[Illus_517_C Debug] Original still exists: {file_path}")
        else:
            if is_target_file:
                print(f"[Illus_517_C Debug] Restoring original from temp: {temp_original} to {file_path}")
            shutil.move(temp_original, file_path)
        return None, "PNG size exceeds 1MB or dimensions not met"

    except Exception as e:
        if is_target_file:
            print(f"[Illus_517_C Debug] Unexpected error processing {file_path}: {str(e)}")
        logger.error(f"Unexpected error processing {file_path}: {str(e)}")
        # Restore original if it was copied
        if temp_original and os.path.exists(temp_original) and not os.path.exists(file_path):
            if is_target_file:
                print(f"[Illus_517_C Debug] Restoring original from temp: {temp_original} to {file_path}")
            shutil.move(temp_original, file_path)
        return None, f"Unexpected error: {str(e)}"
    finally:
        # Clean up temp file if it exists
        if temp_original and os.path.exists(temp_original):
            if is_target_file:
                print(f"[Illus_517_C Debug] Cleaning up temp file: {temp_original}")
            os.remove(temp_original)

if __name__ == "__main__":
    exit(1)