import os
from lxml import etree
from urllib.parse import unquote
import shutil

def find_unreferenced_xmls(ditamap_path, directory_path):
    """
    Find XML files in the directory that are not referenced in the DITA map, excluding LegacyTextTuring.
    
    Args:
        ditamap_path (str): Path to the DITA map file.
        directory_path (str): Root directory containing the DITA map.
    
    Returns:
        list: List of tuples (file_name, folder_path, status) for unreferenced XMLs.
    """
    referenced_files = set()
    xml_files = []
    unreferenced_files = []

    # Parse DITA map to get referenced files
    try:
        tree = etree.parse(ditamap_path)
        hrefs = tree.xpath("//*[self::chapter or self::topicref or self::appendix][@href]/@href")
        ditamap_dir = os.path.dirname(ditamap_path)
        for href in hrefs:
            if href.startswith(('http://', 'https://', 'mailto:')):
                continue
            href = unquote(href)
            full_path = os.path.normpath(os.path.join(ditamap_dir, href))
            if os.path.exists(full_path):
                referenced_files.add(full_path)
    except Exception as e:
        raise Exception(f"Error parsing DITA map: {str(e)}")

    # Collect XML files, excluding LegacyTextTuring
    for root, _, files in os.walk(directory_path):
        if 'LegacyTextTuring' in root.split(os.sep):
            continue
        for file in files:
            if file.endswith(".xml"):
                full_path = os.path.join(root, file)
                xml_files.append(full_path)

    # Find unreferenced XML files
    for xml_path in xml_files:
        if xml_path not in referenced_files and xml_path != ditamap_path:
            file_name = os.path.basename(xml_path)
            folder_path = os.path.relpath(os.path.dirname(xml_path), directory_path).replace(os.sep, "/")
            if folder_path == ".":
                folder_path = ""
            unreferenced_files.append((file_name, folder_path, ""))

    return unreferenced_files

def move_xml_to_trash(full_path, directory_path):
    """
    Move an unreferenced XML file to the LegacyTextTuring folder within the selected directory,
    preserving folder hierarchy. Log the move to LegacyTextTuring/Log.txt with a single header.
    Skip if the file already exists in the destination.
    
    Args:
        full_path (str): Full path to the XML file.
        directory_path (str): Root directory for relative path calculations.
    
    Raises:
        Exception: If the file cannot be moved or logged (except for existing files).
    
    Returns:
        bool: True if operation succeeded or was skipped, False if logging failed.
    """
    if not os.path.exists(full_path):
        raise FileNotFoundError(f"XML file not found: {full_path}")

    # Initialize LegacyTextTuring directory and log file
    legacy_dir = os.path.join(directory_path, "LegacyTextTuring")
    log_file = os.path.join(legacy_dir, "Log.txt")
    log_success = True
    # Track header globally within this module to ensure it's written only once per session
    if not hasattr(move_xml_to_trash, 'header_written'):
        move_xml_to_trash.header_written = False

    try:
        os.makedirs(legacy_dir, exist_ok=True)
        if not os.path.exists(legacy_dir):
            raise OSError(f"Failed to create {legacy_dir}")
    except (OSError, PermissionError) as e:
        log_success = False
        raise Exception(f"Failed to create LegacyTextTuring directory: {str(e)}")

    # Calculate relative path and destination
    rel_path = os.path.relpath(full_path, directory_path).replace(os.sep, "/")
    destination = os.path.join(legacy_dir, rel_path)
    destination_dir = os.path.dirname(destination)

    # Skip if file already exists at destination
    if os.path.exists(destination):
        return True

    try:
        # Create destination directory if it doesn't exist
        os.makedirs(destination_dir, exist_ok=True)
        # Move the file
        shutil.move(full_path, destination)
        # Log the move
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                if not move_xml_to_trash.header_written:
                    f.write("-----------------------------------\nDeleted unreferenced XMLs\n")
                    move_xml_to_trash.header_written = True
                f.write(f"{rel_path} - deleted\n")
        except (OSError, PermissionError) as e:
            log_success = False
            raise Exception(f"Failed to write to log file {log_file}: {str(e)}")
    except Exception as e:
        raise Exception(f"Failed to move XML {os.path.basename(full_path)} to {destination}: {str(e)}")

    return log_success