from PyQt6.QtWidgets import QFileDialog, QWidget
import os
from lxml import etree
import logging
from urllib.parse import unquote, quote

# Set up logging without console output
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
# Use validate_xmls.py's file handler

def remove_duplicate_ids(parent: QWidget, directory_path: str = None) -> tuple[int, int]:
    """
    Ensure unique top-level and nested IDs across XML files, updating references.
    Separates top-level and nested IDs to avoid incorrect duplicate detection.
    Renames duplicates with _1, _2, etc., and updates <xref>/<topicref> hrefs.
    Ignores files in directories containing 'LegacyTextTuring'.
    
    Args:
        parent: The parent widget for the directory dialog.
        directory_path: Optional path to process. If None, a dialog is shown.
    
    Returns:
        tuple: (duplicates_fixed, files_modified)
            - duplicates_fixed: Number of duplicate IDs fixed.
            - files_modified: Number of files modified.
    """
    if not directory_path:
        directory_path = QFileDialog.getExistingDirectory(
            parent, "Select Directory", ""
        )
        if not directory_path:
            return 0, 0

    # Collect .xml and .ditamap files, excluding LegacyTextTuring
    xml_files = []
    ditamap_files = []
    parent_dir = os.path.dirname(directory_path)
    for root, _, files in os.walk(directory_path):
        if 'LegacyTextTuring' in root:
            logger.debug(f"Skipping directory {root}")
            continue
        for file in files:
            if file.endswith(".xml"):
                xml_files.append(os.path.abspath(os.path.join(root, file)).replace('\\', '/'))
    if os.path.exists(parent_dir) and 'LegacyTextTuring' not in parent_dir:
        for file in os.listdir(parent_dir):
            if file.endswith(".ditamap"):
                ditamap_path = os.path.abspath(os.path.join(parent_dir, file)).replace('\\', '/')
                ditamap_files.append(ditamap_path)

    # First pass: Collect top-level and nested IDs separately
    top_id_map = {}  # {id: [file_path]}
    nested_id_map = {}  # {id: [(file_path, parent_top_id)]}
    for file_path in xml_files:
        try:
            tree = etree.parse(file_path)
            root_elem = tree.getroot()
            top_level_id = root_elem.get('id')
            if top_level_id:
                top_id_map.setdefault(top_level_id, []).append(file_path)
            for elem in tree.xpath("//*[@id]"):
                elem_id = elem.get('id')
                if elem_id != top_level_id:
                    nested_id_map.setdefault(elem_id, []).append((file_path, top_level_id or ''))
        except etree.LxmlError:
            logger.debug(f"Skipping malformed XML: {file_path}")
            continue

    # Log ID maps for debugging
    logger.info(f"Top-level ID map: {top_id_map}")
    for id_, entries in top_id_map.items():
        if len(entries) > 1:
            logger.info(f"Duplicate top-level ID {id_} found in: {entries}")
    logger.info(f"Nested ID map: {nested_id_map}")
    for id_, entries in nested_id_map.items():
        if len(entries) > 1:
            logger.info(f"Duplicate nested ID {id_} found in: {entries}")

    # Process duplicates and build rename map
    rename_map = {}  # {orig_id: {file_path: new_id}}
    modified_files = set()
    all_ids = set(top_id_map.keys()).union(nested_id_map.keys())
    duplicates_fixed = 0

    # Handle top-level ID duplicates
    for orig_id, file_paths in top_id_map.items():
        if len(file_paths) > 1:  # Duplicate top-level ID
            for idx, file_path in enumerate(file_paths[1:], 1):  # Keep first unchanged
                n = idx
                new_id = f"{orig_id}_{n}"
                while new_id in all_ids:
                    n += 1
                    new_id = f"{orig_id}_{n}"
                rename_map.setdefault(orig_id, {})[file_path] = new_id
                all_ids.add(new_id)
                modified_files.add(file_path)
                duplicates_fixed += 1
                logger.info(f"Planned top-level rename: {orig_id} -> {new_id} in {file_path}")

    # Handle nested ID duplicates (only if referenced or within same file)
    for orig_id, entries in nested_id_map.items():
        # Group by parent top-level ID to check same-file duplicates
        by_parent = {}
        for file_path, parent_id in entries:
            by_parent.setdefault((file_path, parent_id), []).append(file_path)
        for (file_path, parent_id), paths in by_parent.items():
            if len(paths) > 1:  # Same ID multiple times in same file
                for idx, _ in enumerate(paths[1:], 1):  # Keep first unchanged
                    n = idx
                    new_id = f"{orig_id}_{n}"
                    while new_id in all_ids:
                        n += 1
                        new_id = f"{orig_id}_{n}"
                    rename_map.setdefault(orig_id, {})[file_path] = new_id
                    all_ids.add(new_id)
                    modified_files.add(file_path)
                    duplicates_fixed += 1
                    logger.info(f"Planned nested rename: {orig_id} -> {new_id} in {file_path}")

    # Second pass: Update modified files and references
    files_modified = 0
    # Update modified files
    for file_path in modified_files:
        try:
            tree = etree.parse(file_path)
            root_elem = tree.getroot()
            modified = False
            
            # Update top-level ID
            orig_top_id = root_elem.get('id')
            if orig_top_id in rename_map and file_path in rename_map[orig_top_id]:
                new_top_id = rename_map[orig_top_id][file_path]
                root_elem.set('id', new_top_id)
                logger.info(f"Updated root ID in {file_path}: {orig_top_id} -> {new_top_id}")
                modified = True
            
            # Update nested IDs
            for elem in tree.xpath("//*[@id]"):
                elem_id = elem.get('id')
                if elem_id in rename_map and file_path in rename_map[elem_id]:
                    new_id = rename_map[elem_id][file_path]
                    elem.set('id', new_id)
                    logger.info(f"Updated nested ID in {file_path}: {elem_id} -> {new_id}")
                    modified = True
            
            # Update internal <xref> hrefs
            for xref in tree.xpath("//xref[@href]"):
                href = xref.get('href')
                if href.startswith('#'):
                    if '/' in href:  # Format: #top_id/nested_id
                        parts = href[1:].split('/', 1)
                        if len(parts) == 2:
                            href_top_id, href_nested_id = parts
                            new_href = href
                            if href_top_id == orig_top_id and orig_top_id in rename_map and file_path in rename_map[orig_top_id]:
                                new_href = f"#{rename_map[orig_top_id][file_path]}/{href_nested_id}"
                            if href_nested_id in rename_map and file_path in rename_map[href_nested_id]:
                                new_href = f"#{href_top_id if new_href == href else rename_map[orig_top_id][file_path]}/{rename_map[href_nested_id][file_path]}"
                            if new_href != href:
                                xref.set('href', new_href)
                                logger.info(f"Updated internal xref in {file_path}: {href} -> {new_href}")
                                modified = True
                    else:  # Format: #id (top-level or nested)
                        href_id = href[1:]
                        if href_id in rename_map and file_path in rename_map[href_id]:
                            new_href = f"#{rename_map[href_id][file_path]}"
                            xref.set('href', new_href)
                            logger.info(f"Updated internal xref in {file_path}: {href} -> {new_href}")
                            modified = True
            
            if modified:
                tree.write(file_path, encoding=tree.docinfo.encoding,
                         doctype=tree.docinfo.doctype, pretty_print=False,
                         xml_declaration=True)
                files_modified += 1
                logger.info(f"Saved modified file: {file_path}")
                
        except etree.LxmlError:
            logger.debug(f"Skipping malformed XML: {file_path}")
            continue
        except OSError as e:
            logger.error(f"Failed to write {file_path}: {str(e)}")
            continue

    # Update cross-file <xref> and DITA map references
    for file_path in xml_files + ditamap_files:
        try:
            tree = etree.parse(file_path)
            modified = False
            elements = tree.xpath("//xref[@href]|//topicref[@href]")
            for elem in elements:
                href = elem.get('href')
                if '#' in href and not href.startswith('#'):
                    filename, ref_id = href.split('#', 1)
                    filename = unquote(filename)
                    abs_file_path = os.path.abspath(os.path.join(os.path.dirname(file_path), filename)).replace('\\', '/')
                    if abs_file_path in xml_files:
                        if '/' in ref_id:  # Format: top_id/nested_id
                            top_id, nested_id = ref_id.split('/', 1)
                            new_ref_id = ref_id
                            if top_id in rename_map and abs_file_path in rename_map[top_id]:
                                new_ref_id = f"{rename_map[top_id][abs_file_path]}/{nested_id}"
                            if nested_id in rename_map and abs_file_path in rename_map[nested_id]:
                                new_ref_id = f"{top_id if new_ref_id == ref_id else rename_map[top_id][abs_file_path]}/{rename_map[nested_id][abs_file_path]}"
                            if new_ref_id != ref_id:
                                new_href = f"{quote(filename, safe='/')}#{new_ref_id}"
                                elem.set('href', new_href)
                                logger.info(f"Updated reference in {file_path}: {href} -> {new_href}")
                                modified = True
                        else:  # Format: id
                            if ref_id in rename_map and abs_file_path in rename_map[ref_id]:
                                new_href = f"{quote(filename, safe='/')}#{rename_map[ref_id][abs_file_path]}"
                                elem.set('href', new_href)
                                logger.info(f"Updated reference in {file_path}: {href} -> {new_href}")
                                modified = True
            
            if modified:
                tree.write(file_path, encoding=tree.docinfo.encoding,
                         doctype=tree.docinfo.doctype, pretty_print=False,
                         xml_declaration=True)
                files_modified += 1
                logger.info(f"Saved modified file for references: {file_path}")
                
        except etree.LxmlError:
            logger.debug(f"Skipping malformed XML/DITA map: {file_path}")
            continue
        except OSError as e:
            logger.error(f"Failed to write {file_path}: {str(e)}")
            continue

    return duplicates_fixed, files_modified