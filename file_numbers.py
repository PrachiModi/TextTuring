import os
import shutil
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def analyze_files(directory_path):
    """
    Analyze files in the directory by extension, excluding LegacyTextTuring folder.
    
    Args:
        directory_path (str): Directory to analyze.
    
    Returns:
        list: List of tuples (file_type, count, action).
    """
    file_counts = {}
    
    try:
        for root, _, files in os.walk(directory_path):
            if 'LegacyTextTuring' in root.split(os.sep):
                logger.debug(f"Skipping LegacyTextTuring directory: {root}")
                continue
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext:  # Only count files with extensions
                    file_counts[ext] = file_counts.get(ext, 0) + 1
    except Exception as e:
        logger.error(f"Error analyzing files in {directory_path}: {str(e)}")
        return []

    results = [(ext, count, "View") for ext, count in file_counts.items()]
    results.sort(key=lambda x: x[0])  # Sort by extension
    return results

def get_files_by_type(directory_path, file_type):
    """
    Get files of a specific type in the directory, excluding LegacyTextTuring folder.
    
    Args:
        directory_path (str): Directory to search.
        file_type (str): File extension (e.g., '.xml').
    
    Returns:
        list: List of tuples (file_name, folder_path, action).
    """
    files_list = []
    file_type = file_type.lower()

    try:
        for root, _, files in os.walk(directory_path):
            if 'LegacyTextTuring' in root.split(os.sep):
                logger.debug(f"Skipping LegacyTextTuring directory: {root}")
                continue
            for file in files:
                if file.lower().endswith(file_type):
                    file_name = file
                    folder_path = os.path.relpath(root, directory_path).replace(os.sep, "/")
                    if folder_path == ".":
                        folder_path = ""
                    files_list.append((file_name, folder_path, "Delete"))
    except Exception as e:
        logger.error(f"Error getting files of type {file_type} in {directory_path}: {str(e)}")
        return [("Error", str(e), "")]

    if not files_list:
        return []
    
    files_list.sort(key=lambda x: x[0])  # Sort by file name
    return files_list

def move_file_to_trash(full_path, directory_path):
    """
    Move a file to the LegacyTextTuring folder within the selected directory.
    Log the action to LegacyTextTuring/Log.txt with a single header.
    
    Args:
        full_path (str): Full path to the file.
        directory_path (str): Root directory for relative path calculations.
    
    Raises:
        Exception: If the file cannot be moved.
    """
    if not os.path.exists(full_path):
        raise FileNotFoundError(f"File not found: {full_path}")

    legacy_dir = os.path.join(directory_path, "LegacyTextTuring")
    os.makedirs(legacy_dir, exist_ok=True)

    file_name = os.path.basename(full_path)
    destination = os.path.join(legacy_dir, file_name)

    # Prepare log file
    log_file = os.path.join(legacy_dir, "Log.txt")
    log_success = True
    header_written = os.path.exists(log_file) and os.path.getsize(log_file) > 0

    try:
        # Move the file
        shutil.move(full_path, destination)
        logger.debug(f"Successfully moved {full_path} to {destination}")

        # Log the action
        rel_path = os.path.relpath(full_path, directory_path).replace(os.sep, "/")
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                if not header_written:
                    f.write("-----------------------------\nFile Deletion Log:\n")
                f.write(f"{rel_path} - Deleted and moved to LegacyTextTuring\n")
        except (OSError, PermissionError) as e:
            logger.error(f"Failed to write to log file {log_file}: {str(e)}")
            log_success = False

    except Exception as e:
        logger.error(f"Failed to move {full_path} to {destination}: {str(e)}")
        raise Exception(f"Failed to move file {file_name} to LegacyTextTuring: {str(e)}")

    return log_success