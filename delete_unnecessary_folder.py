import os
import re
import shutil
from pathlib import Path
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

def is_folder_empty(folder_path):
    """Check if a folder is empty, ignoring hidden files."""
    for item in Path(folder_path).iterdir():
        if not item.name.startswith('.'):
            return False
    return True

def delete_unnecessary_folders(directory):
    """Scan directory for 'out', 'temp', or empty folders, excluding LegacyTextTuring."""
    results = []
    legacy_dir = os.path.join(directory, "LegacyTextTuring")
    for root, dirs, _ in os.walk(directory):
        # Skip LegacyTextTuring directory
        if root.startswith(legacy_dir):
            logging.debug(f"Skipping LegacyTextTuring directory: {root}")
            continue
        logging.debug(f"Scanning root: {root}, dirs: {dirs}")
        for dir_name in dirs[:]:  # Copy to avoid modifying during iteration
            full_path = os.path.join(root, dir_name)
            relative_path = os.path.relpath(full_path, directory)
            out_temp_match = re.match(r'^(out|temp)$', dir_name, re.IGNORECASE)
            is_empty = is_folder_empty(full_path)
            if out_temp_match or is_empty:
                logging.debug(f"Adding folder: {dir_name}, Path: {relative_path}, Full Path: {full_path}, Out/Temp: {out_temp_match}, Empty: {is_empty}")
                results.append((dir_name, relative_path, "Delete"))
            else:
                non_hidden_contents = [item.name for item in Path(full_path).iterdir() if not item.name.startswith('.')]
                logging.debug(f"Skipping folder: {dir_name}, Path: {relative_path}, Non-hidden Contents: {non_hidden_contents}")
    logging.debug(f"Found {len(results)} folders")
    return results

def move_folder_contents_to_trash(folder_path, base_dir):
    """Move folder to LegacyTextTuring with unique naming to avoid conflicts."""
    logger = logging.getLogger(__name__)
    folder_name = os.path.basename(folder_path)
    legacy_dir = os.path.join(base_dir, "LegacyTextTuring")
    os.makedirs(legacy_dir, exist_ok=True)
    
    # Generate base destination path with timestamp
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    base_dest_dir = os.path.join(legacy_dir, f"{folder_name}_{timestamp}")
    dest_dir = base_dest_dir
    counter = 1
    
    # Find a unique destination path
    while os.path.exists(dest_dir):
        dest_dir = f"{base_dest_dir}_{counter}"
        counter += 1
    
    logger.debug(f"Attempting to move folder: {folder_path}")
    try:
        # Move the entire folder to the unique destination
        shutil.move(folder_path, dest_dir)
        logger.debug(f"Successfully moved {folder_path} to {dest_dir}")
    except Exception as e:
        logger.error(f"Failed to move {folder_path} to {dest_dir}: {str(e)}")
        raise Exception(f"Failed to move folder {folder_name} to LegacyTextTuring: {str(e)}")