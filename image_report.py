import os
from PIL import Image, UnidentifiedImageError
import logging

logger = logging.getLogger(__name__)

def scan_images_for_resizing(directory_path: str) -> tuple:
    """
    Scan the directory and subfolders for JPEG and PNG images, identifying those needing
    resizing based on width > 1000px, height > 1000px, or size > 1MB, skipping LegacyTextTuring, out, and temp folders.

    Args:
        directory_path: Path to the directory to scan.

    Returns:
        tuple: (image_list, total_images_scanned, images_to_be_resized)
            - image_list: List of tuples (file_path, relative_path, reason) for images needing action.
            - total_images_scanned: Total number of JPEG and PNG images scanned.
            - images_to_be_resized: Number of images needing resizing.
    """
    image_list = []
    total_images_scanned = 0
    images_to_be_resized = 0
    skip_folders = {"legacytextturing", "out", "temp"}  # Case-insensitive set

    for root, dirs, files in os.walk(directory_path, topdown=True):
        # Skip specified folders
        if os.path.basename(root).lower() in skip_folders:
            logger.debug(f"Skipping folder: {root}")
            continue
        try:
            for file in sorted(files):  # Sort files alphabetically
                if file.lower().endswith((".jpg", ".jpeg", ".png")):
                    total_images_scanned += 1
                    file_path = os.path.join(root, file)
                    # Get relative path
                    relative_path = os.path.relpath(root, directory_path).replace(os.sep, "/")
                    if relative_path == ".":
                        relative_path = ""
                    else:
                        relative_path += "/"
                    try:
                        # Check image dimensions and file size
                        with Image.open(file_path) as img:
                            width, height = img.size
                        file_size_bytes = os.path.getsize(file_path)
                        file_size_mb = file_size_bytes / (1024 * 1024)

                        # Collect reasons for needing resizing
                        reasons = []
                        if width > 1000:
                            reasons.append("Width > 1000px")
                        if height > 1000:
                            reasons.append("Height > 1000px")
                        if file_size_mb > 1:
                            reasons.append("File size > 1MB")

                        # If there are reasons, add to the list
                        if reasons:
                            images_to_be_resized += 1
                            reason_text = ", ".join(reasons)
                            image_list.append((file_path, relative_path, reason_text))
                    except UnidentifiedImageError:
                        images_to_be_resized += 1
                        image_list.append((file_path, relative_path, "Corrupted"))
                    except PermissionError:
                        images_to_be_resized += 1
                        image_list.append((file_path, relative_path, "Permission denied"))
        except PermissionError as e:
            logger.error(f"Error accessing directory {root}: {str(e)}")
            continue  # Skip inaccessible subfolders

    return image_list, total_images_scanned, images_to_be_resized