import os
from lxml import etree
from urllib.parse import unquote
import shutil

def find_unreferenced_graphics(ditamap_path, directory_path):
    """
    Find PNG, JPG, and JPEG images in the Graphics folder that are not referenced in the DITA map or its XML files,
    excluding LegacyTextTuring.
    
    Args:
        ditamap_path (str): Path to the DITA map file.
        directory_path (str): Root directory containing the DITA map and Graphics folder.
    
    Returns:
        list: List of tuples (file_name, folder_path, status) for unreferenced images.
    """
    referenced_images = set()
    unreferenced_images = []

    # Parse DITA map to get referenced XML files
    try:
        tree = etree.parse(ditamap_path)
        xml_hrefs = tree.xpath("//*[self::chapter or self::topicref or self::appendix][@href]/@href")
        xml_hrefs = [unquote(href) for href in xml_hrefs if href and not href.startswith(('http://', 'https://', 'mailto:'))]
    except Exception as e:
        raise Exception(f"Error parsing DITA map: {str(e)}")

    # Collect XML files from all subdirectories, excluding LegacyTextTuring
    xml_files = []
    for root, _, files in os.walk(directory_path):
        if 'LegacyTextTuring' in root.split(os.sep):
            continue
        for file in files:
            if file.endswith(".xml"):
                xml_files.append(os.path.join(root, file))

    # Parse referenced XML files for <image> elements
    ditamap_dir = os.path.dirname(ditamap_path)
    for href in xml_hrefs:
        xml_path = os.path.normpath(os.path.join(ditamap_dir, href))
        if os.path.exists(xml_path) and xml_path in xml_files:
            try:
                xml_tree = etree.parse(xml_path)
                image_hrefs = xml_tree.xpath("//image/@href")
                for image_href in image_hrefs:
                    image_path = os.path.normpath(os.path.join(os.path.dirname(xml_path), unquote(image_href)))
                    if image_path.lower().endswith((".png", ".jpg", ".jpeg")):
                        referenced_images.add(image_path)
            except Exception as e:
                print(f"Warning: Error parsing XML file {xml_path}: {str(e)}")

    # Collect PNG, JPG, and JPEG files from Graphics folder, excluding LegacyTextTuring
    graphics_dir = os.path.join(directory_path, "Graphics")
    if os.path.exists(graphics_dir):
        for root, _, files in os.walk(graphics_dir):
            if 'LegacyTextTuring' in root.split(os.sep):
                continue
            for file in files:
                if file.lower().endswith((".png", ".jpg", ".jpeg")):
                    full_path = os.path.join(root, file)
                    if full_path not in referenced_images:
                        relative_path = os.path.relpath(root, directory_path).replace(os.sep, "/")
                        unreferenced_images.append((file, relative_path, ""))
    else:
        print(f"Warning: Graphics directory not found: {graphics_dir}")

    return unreferenced_images

def move_graphic_to_trash(full_path, directory_path):
    """
    Move an unreferenced graphic file to LegacyTextTuring/Graphics within the selected directory,
    handling filename conflicts by appending a suffix. Log the move to LegacyTextTuring/Log.txt with a single header.
    Skip if the file already exists in the destination with the same name and suffix.
    
    Args:
        full_path (str): Full path to the graphic file.
        directory_path (str): Root directory for relative path calculations.
    
    Raises:
        Exception: If the file cannot be moved or logged (except for existing files).
    
    Returns:
        bool: True if operation succeeded or was skipped, False if logging failed.
    """
    if not os.path.exists(full_path):
        raise FileNotFoundError(f"Graphic file not found: {full_path}")

    # Initialize LegacyTextTuring/Graphics directory and log file
    legacy_graphics_dir = os.path.join(directory_path, "LegacyTextTuring", "Graphics")
    log_file = os.path.join(directory_path, "LegacyTextTuring", "Log.txt")
    log_success = True
    # Track header globally within this module to ensure it's written only once per session
    if not hasattr(move_graphic_to_trash, 'header_written'):
        move_graphic_to_trash.header_written = False

    try:
        os.makedirs(legacy_graphics_dir, exist_ok=True)
        if not os.path.exists(legacy_graphics_dir):
            raise OSError(f"Failed to create {legacy_graphics_dir}")
    except (OSError, PermissionError) as e:
        log_success = False
        raise Exception(f"Failed to create LegacyTextTuring/Graphics directory: {str(e)}")

    # Calculate relative path for logging and destination path
    rel_path = os.path.relpath(full_path, directory_path).replace(os.sep, "/")
    file_name = os.path.basename(full_path)
    base, ext = os.path.splitext(file_name)
    destination = os.path.join(legacy_graphics_dir, file_name)

    # Handle filename conflicts by appending a suffix
    counter = 1
    while os.path.exists(destination):
        new_file_name = f"{base}_{counter}{ext}"
        destination = os.path.join(legacy_graphics_dir, new_file_name)
        counter += 1

    try:
        # Move the file
        shutil.move(full_path, destination)
        # Log the move
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                if not move_graphic_to_trash.header_written:
                    f.write("-----------------------------\nDeleted Unreferenced Graphics\n")
                    move_graphic_to_trash.header_written = True
                f.write(f"{rel_path} - deleted\n")
        except (OSError, PermissionError) as e:
            log_success = False
            raise Exception(f"Failed to write to log file {log_file}: {str(e)}")
    except Exception as e:
        raise Exception(f"Failed to move graphic {file_name} to {destination}: {str(e)}")

    return log_success