import os
from lxml import etree
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count

def _process_xml_file(args):
    """
    Process a single XML file for graphics validation.
    
    Args:
        args: Tuple of (file_path, directory_path)
        
    Returns:
        list: List of tuples (relative_path, status, figure_title) for images with issues in this file.
    """
    file_path, directory_path = args
    results = []
    
    try:
        # Parse the XML file
        tree = etree.parse(file_path)
        # Find all <image> elements
        images = tree.xpath("//image")
        for image in images:
            # Initialize status list for concatenation
            status_parts = []

            # Check width attribute
            width = image.get("width")
            if not width:
                status_parts.append("Width not set")
            else:
                # Parse width for value and unit
                width_match = re.match(r"^(\d*\.?\d+)([a-zA-Z*]+)?$", width)
                if not width_match:
                    status_parts.append("Invalid width format")
                else:
                    value_str, unit = width_match.groups()
                    unit = unit or ""  # Handle cases where unit is missing
                    try:
                        width_value = float(value_str)
                        if unit != "in":
                            status_parts.append(f"Width set to {width}{unit}, invalid unit")
                        elif width_value > 6.75:
                            status_parts.append("Width more than 6.75in")
                    except ValueError:
                        status_parts.append("Invalid width format")

            # Check scope attribute
            scope = image.get("scope")
            if scope == "external":
                status_parts.append("Invalid external scope")

            # Check scale attribute
            scale = image.get("scale")
            if scale and scale.strip():
                status_parts.append("Remove Image scale")

            # Check for parent <fig> and its <title>
            parent_fig = image.xpath("parent::fig")
            figure_title = "Missing Image Title"
            has_valid_title = False
            if parent_fig:
                title = parent_fig[0].xpath("title")
                if title and title[0].text and title[0].text.strip():
                    figure_title = "---"
                    has_valid_title = True

            # Skip images with no issues
            if not status_parts and has_valid_title:
                continue

            # Combine status messages
            status = "; ".join(status_parts) if status_parts else "---"

            # Compute relative path
            relative_path = os.path.relpath(file_path, directory_path)
            results.append((relative_path, status, figure_title))
    except etree.LxmlError:
        pass  # Skip malformed XML files
    
    return results

def validate_graphics(directory_path: str, use_multiprocessing: bool = True) -> list:
    """
    Scan all XML files in the given directory and its subfolders to validate <image> elements.
    Validates width (presence, unit, value), scope, scale, and figure title.
    Returns images with issues, omitting images with valid width, scope, scale, and non-empty figure title.

    Args:
        directory_path: Path to the directory containing XML files.
        use_multiprocessing: Whether to use parallel processing (default: True).

    Returns:
        list: List of tuples (relative_path, status, figure_title) for each image with issues.
              relative_path: Path relative to directory_path.
              status: Concatenated issues ("Width not set", "Invalid width format", 
                      "Width set to [value][unit], invalid unit", "Width more than 6.75in",
                      "Invalid external scope", "Remove Image scale").
              figure_title: "---" if parent <fig> has non-empty <title>, else "Missing Image Title".
    """
    # Collect all XML files recursively
    xml_files = []
    for root, _, files in os.walk(directory_path):
        for file in files:
            if file.endswith(".xml"):
                file_path = os.path.join(root, file)
                xml_files.append((file_path, directory_path))
    
    if not xml_files:
        return []
    
    results = []
    
    if use_multiprocessing and len(xml_files) > 1:
        # Use multiprocessing for better performance
        max_workers = min(cpu_count(), len(xml_files))
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_process_xml_file, args): args for args in xml_files}
            for future in as_completed(futures):
                try:
                    file_results = future.result()
                    results.extend(file_results)
                except Exception:
                    pass  # Skip files that cause errors
    else:
        # Single-threaded processing
        for args in xml_files:
            file_results = _process_xml_file(args)
            results.extend(file_results)

    return results