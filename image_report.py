import os
from PIL import Image, UnidentifiedImageError
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count

logger = logging.getLogger(__name__)

def _process_image_file(args):
    """
    Process a single image file for validation.
    
    Args:
        args: Tuple of (file_path, relative_path)
        
    Returns:
        tuple: (relative_path, reason) if image needs action, None otherwise.
    """
    file_path, relative_path = args
    file = os.path.basename(file_path)
    
    try:
        # Check image dimensions and file size
        with Image.open(file_path) as img:
            width, height = img.size
            dpi = img.info.get('dpi', (0, 0))
        file_size_bytes = os.path.getsize(file_path)
        file_size_mb = file_size_bytes / (1024 * 1024)

        # Collect reasons for needing resizing
        reasons = []
        if width > 972:
            reasons.append("Width > 972px")
        if height > 972:
            reasons.append("Height > 972px")
        if file_size_mb > 1:
            reasons.append("File size > 1MB")
        if not file.lower().endswith(".png"):
            reasons.append("Not PNG")
        if dpi != (144, 144):
            reasons.append("DPI !=144")

        # If there are reasons, return the issue
        if reasons:
            reason_text = ", ".join(reasons)
            return (file_path, relative_path, reason_text)
    except UnidentifiedImageError:
        return (file_path, relative_path, "Corrupted")
    except PermissionError:
        return (file_path, relative_path, "Permission denied")
    except Exception:
        pass
    
    return None

def scan_images_for_resizing(directory_path: str, use_multiprocessing: bool = True) -> tuple:
    """
    Scan the directory and subfolders for JPEG and PNG images, identifying those needing
    resizing based on width > 972px, height > 972px, or size > 1MB, not PNG, DPI !=144, skipping LegacyTextTuring, out, and temp folders.

    Args:
        directory_path: Path to the directory to scan.
        use_multiprocessing: Whether to use parallel processing (default: True).

    Returns:
        tuple: (image_list, total_images_scanned, images_to_be_resized)
            - image_list: List of tuples (file_path, relative_path, reason) for images needing action.
            - total_images_scanned: Total number of JPEG and PNG images scanned.
            - images_to_be_resized: Number of images needing resizing.
    """
    image_list = []
    skip_folders = {"legacytextturing", "out", "temp"}  # Case-insensitive set

    # Collect all image files recursively
    image_files = []
    for root, dirs, files in os.walk(directory_path, topdown=True):
        # Skip specified folders
        if os.path.basename(root).lower() in skip_folders:
            logger.debug(f"Skipping folder: {root}")
            continue
        try:
            for file in sorted(files):  # Sort files alphabetically
                if file.lower().endswith((".jpg", ".jpeg", ".png")):
                    file_path = os.path.join(root, file)
                    # Get relative path
                    relative_path = os.path.relpath(root, directory_path).replace(os.sep, "/")
                    if relative_path == ".":
                        relative_path = ""
                    else:
                        relative_path += "/"
                    image_files.append((file_path, relative_path))
        except PermissionError as e:
            logger.error(f"Error accessing directory {root}: {str(e)}")
            continue  # Skip inaccessible subfolders

    total_images_scanned = len(image_files)
    
    if not image_files:
        return [], 0, 0
    
    if use_multiprocessing and len(image_files) > 1:
        # Use multiprocessing for better performance
        max_workers = min(cpu_count(), len(image_files))
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_process_image_file, args): args for args in image_files}
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        image_list.append(result)
                except Exception:
                    pass  # Skip files that cause errors
    else:
        # Single-threaded processing
        for args in image_files:
            result = _process_image_file(args)
            if result:
                image_list.append(result)

    images_to_be_resized = len(image_list)
    return image_list, total_images_scanned, images_to_be_resized