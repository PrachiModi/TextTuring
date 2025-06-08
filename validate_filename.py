import os
from lxml import etree
import re
from typing import List, Tuple
import logging

# Set up logging (file-only, matches validate_xmls.py)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def validate_filename(directory_path: str) -> List[Tuple[str, str, str]]:
    """
    Validates that XML filenames match their title elements.
    
    Args:
        directory_path: Directory containing XML files to validate
        
    Returns:
        List of tuples (relative_path, title, new_path) for files with mismatched names
    """
    def normalize_string(s: str) -> str:
        s = s.lower()
        s = re.sub(r'[^a-z0-9]', '', s)
        return s
    
    results = []
    
    for root, _, files in os.walk(directory_path):
        for file in files:
            if file.endswith(".xml"):
                file_path = os.path.join(root, file)
                try:
                    tree = etree.parse(file_path)
                    title_elem = tree.find(".//title")
                    if title_elem is None or not title_elem.text:
                        logger.debug(f"Skipping {file_path}: No title element or empty title")
                        continue
                    title = title_elem.text.strip()
                    normalized_title = normalize_string(title)
                    file_name = os.path.splitext(file)[0]
                    normalized_file_name = normalize_string(file_name)
                    if normalized_file_name != normalized_title:
                        relative_path = os.path.relpath(file_path, directory_path)
                        results.append((relative_path, title, relative_path))
                        logger.info(f"Filename mismatch: {file_path}, File Name: {file_name}, Title: {title}")
                except etree.LxmlError:
                    logger.debug(f"Skipping malformed XML: {file_path}")
                    continue
    
    return results