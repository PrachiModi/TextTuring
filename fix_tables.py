import os
from lxml import etree

def validate_tables(directory_path: str) -> list:
    """
    Scan all XML files in the given directory and its subfolders to validate tables.
    Only returns tables with issues (missing title, total width > 6 inches, or width not specified).
    
    Args:
        directory_path: Path to the directory containing XML files.
    
    Returns:
        list: List of tuples (relative_path, table_caption, width_issue) for each table with issues.
              relative_path is the path relative to directory_path, table_caption is "----" if missing,
              width_issue is "Table Width > 6inches", "Width Not Specified", or empty.
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
                    # Find all <table> elements
                    tables = tree.xpath("//table")
                    for table in tables:
                        # Check for <title> tag
                        title_elem = table.find("title")
                        table_caption = title_elem.text if title_elem is not None and title_elem.text else "----"
                        has_title = title_elem is not None and title_elem.text

                        # Check total column width
                        tgroup = table.find("tgroup")
                        width_specified = False
                        total_width = 0.0
                        if tgroup is not None:
                            colspecs = tgroup.findall("colspec")
                            if colspecs:  # Check if there are any colspec elements
                                for colspec in colspecs:
                                    colwidth = colspec.get("colwidth")
                                    if colwidth:
                                        # Extract numeric value (e.g., "1in" -> 1.0)
                                        try:
                                            width = float(colwidth.replace("in", ""))
                                            total_width += width
                                            width_specified = True
                                        except ValueError:
                                            continue  # Skip invalid colwidth values

                        # Determine width issue
                        width_issue = ""
                        if not width_specified:
                            width_issue = "Width Not Specified"
                        elif total_width > 6.0:
                            width_issue = "Table Width > 6inches"

                        # Only include tables with at least one issue (missing title or width issue)
                        if not has_title or width_issue:
                            # Compute the relative path from directory_path to file_path
                            relative_path = os.path.relpath(file_path, directory_path)
                            results.append((relative_path, table_caption, width_issue))
                except etree.LxmlError:
                    continue  # Skip malformed XML files

    return results