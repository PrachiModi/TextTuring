import os
from lxml import etree

def validate_graphics(directory_path: str) -> list:
    """
    Scan all XML files in the given directory and its subfolders to validate <image> elements.
    Returns images with issues (missing height, width, or figure title), omitting images with
    height, width, and a non-empty figure title all set.
    
    Args:
        directory_path: Path to the directory containing XML files.
    
    Returns:
        list: List of tuples (relative_path, status, figure_title) for each image with issues.
              relative_path is the path relative to directory_path, status is "Height not set",
              "Width not set", "Height and Width not set", or "---" (if height and width are set),
              figure_title is "---" if the parent <fig> has a non-empty <title>, or
              "Missing Image Title" if <fig> is missing or <title> is absent/empty.
    """
    results = []

    # Collect all XML files recursively
    for root, _, files in os.walk(directory_path):
        for file in files:
            if file.endswith(".xml"):
                file_path = os.path.join(root, file)
                try:
                    # Parse the XML file
                    tree = etree.parse(file_path)
                    # Find all <image> elements
                    images = tree.xpath("//image")
                    for image in images:
                        # Check for height and width attributes
                        height = image.get("height")
                        width = image.get("width")
                        status = ""
                        if not height and not width:
                            status = "Height and Width not set"
                        elif not height:
                            status = "Height not set"
                        elif not width:
                            status = "Width not set"
                        else:
                            status = "---"

                        # Check for parent <fig> and its <title>
                        parent_fig = image.xpath("parent::fig")
                        figure_title = "Missing Image Title"
                        has_valid_title = False
                        if parent_fig:
                            title = parent_fig[0].xpath("title")
                            if title and title[0].text and title[0].text.strip():
                                figure_title = "---"
                                has_valid_title = True

                        # Skip images with height, width, and non-empty title all set
                        if status == "---" and has_valid_title:
                            continue

                        # Compute the relative path from directory_path to file_path
                        relative_path = os.path.relpath(file_path, directory_path)
                        results.append((relative_path, status, figure_title))
                except etree.LxmlError:
                    continue  # Skip malformed XML files

    return results