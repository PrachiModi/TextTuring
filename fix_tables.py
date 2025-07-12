import os
from lxml import etree
import re

def validate_tables(directory_path: str) -> list:
    """
    Scan all XML files in the given directory and its subfolders to validate tables.
    Only returns tables with issues (missing title, total width > 6 inches or > 460 points, or width not specified).
    Tables with any colwidth="1*" are not flagged for width issues.
    
    Args:
        directory_path: Path to the directory containing XML files.
    
    Returns:
        list: List of tuples (relative_path, table_title, width_issue) for each table with issues.
              relative_path is the path relative to directory_path, table_title is "---" if title exists,
              "Missing Table Title" if missing or empty, width_issue is "Table Width > 6inches",
              "Table Width > 460pt", "Width Not Specified", or "---" if width is specified and within limits
              or if colwidth="1*".
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
                        table_title = "---" if title_elem is not None and title_elem.text and title_elem.text.strip() else "Missing Table Title"
                        has_title = title_elem is not None and title_elem.text and title_elem.text.strip()

                        # Check total column width
                        tgroup = table.find("tgroup")
                        width_specified = False
                        total_width_in = 0.0
                        total_width_pt = 0.0
                        has_proportional_width = False
                        if tgroup is not None:
                            colspecs = tgroup.findall("colspec")
                            if colspecs:  # Check if there are any colspec elements
                                for colspec in colspecs:
                                    colwidth = colspec.get("colwidth")
                                    if colwidth:
                                        colwidth = colwidth.strip()
                                        if colwidth == "1*":
                                            has_proportional_width = True
                                            width_specified = True
                                            continue
                                        # Extract numeric value and unit (e.g., "1 in" -> 1.0, "in"; "100 pt" -> 100.0, "pt")
                                        match = re.match(r"(\d*\.?\d+)\s*(in|pt)", colwidth)
                                        if match:
                                            value = float(match.group(1))
                                            unit = match.group(2)
                                            if unit == "in":
                                                total_width_in += value
                                            elif unit == "pt":
                                                total_width_pt += value
                                            width_specified = True

                        # Determine width issue
                        width_issue = ""
                        if has_proportional_width:
                            width_issue = "---"  # No width issues if colwidth="1*"
                        elif not width_specified:
                            width_issue = "Width Not Specified"
                        else:
                            # Convert to points for consistent check (1in = 72pt)
                            total_width_pt = total_width_pt + (total_width_in * 72.0)
                            if total_width_pt > 460.0:
                                width_issue = "Table Width > 460pt"
                            elif total_width_in > 0 and total_width_in > 6.0 and total_width_pt <= 460.0:
                                width_issue = "Table Width > 6inches"
                            else:
                                width_issue = "---"

                        # Only include tables with at least one issue (missing title or width issue)
                        if not has_title or width_issue in ["Table Width > 6inches", "Table Width > 460pt", "Width Not Specified"]:
                            # Compute the relative path from directory_path to file_path
                            relative_path = os.path.relpath(file_path, directory_path)
                            results.append((relative_path, table_title, width_issue))
                except etree.LxmlError:
                    continue  # Skip malformed XML files

    return results