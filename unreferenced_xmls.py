import os
from lxml import etree
from urllib.parse import unquote

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
    Move an unreferenced XML file to the LegacyTextTuring folder within the selected directory.
    
    Args:
        full_path (str): Full path to the XML file.
        directory_path (str): Root directory for relative path calculations.
    
    Raises:
        Exception: If the file cannot be moved.
    """
    if not os.path.exists(full_path):
        raise FileNotFoundError(f"XML file not found: {full_path}")

    legacy_dir = os.path.join(directory_path, "LegacyTextTuring")
    os.makedirs(legacy_dir, exist_ok=True)

    file_name = os.path.basename(full_path)
    destination = os.path.join(legacy_dir, file_name)

    try:
        import shutil
        shutil.move(full_path, destination)
    except Exception as e:
        raise Exception(f"Failed to move XML {file_name} to LegacyTextTuring: {str(e)}")