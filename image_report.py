import os
from PIL import Image, UnidentifiedImageError

def scan_images_for_resizing(directory_path: str) -> tuple:
    """
    Scan the directory and subfolders for JPEG and PNG images, identifying those needing
    resizing or conversion based on size criteria.

    Args:
        directory_path: Path to the directory to scan.

    Returns:
        tuple: (image_list, total_images_scanned, images_to_be_resized)
            - image_list: List of tuples (file_path, relative_path, reason) for images needing action.
            - total_images_scanned: Total number of JPEG and PNG images scanned.
            - images_to_be_resized: Number of images needing resizing or conversion.
    """
    image_list = []
    total_images_scanned = 0
    images_to_be_resized = 0

    for root, dirs, files in os.walk(directory_path, topdown=True):
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

                        # Collect reasons for needing resizing/conversion
                        reasons = []
                        if width >= 1000:
                            reasons.append("Width too large")
                        if height >= 1000:
                            reasons.append("Height too large")
                        if file_size_mb > 1:
                            reasons.append("File size > 1MB")
                        if file.lower().endswith((".jpg", ".jpeg")):
                            reasons.append("JPEG format")

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
        except PermissionError:
            continue  # Skip inaccessible subfolders

    return image_list, total_images_scanned, images_to_be_resized