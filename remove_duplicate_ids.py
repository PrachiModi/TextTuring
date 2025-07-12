from PyQt6.QtWidgets import QFileDialog, QWidget
import os
import time
from lxml import etree
from urllib.parse import unquote, quote
import shutil

def remove_duplicate_ids(parent: QWidget, dir_path: str = None) -> tuple[int, int, bool]:
    """
    Ensure unique top-level and nested IDs across XML and DITA files, updating references.
    Renames duplicates with ttu_ prefix and _n suffix. Ignores 'LegacyTextTuring' directories.
    Backs up files with modified links to LegacyTextTuring, preserving folder hierarchy,
    skipping if backup exists. Logs link changes to LegacyTextTuring/Log.txt with a single header.
    Preserves original href filename encoding using href.split.
    
    Args:
        parent: Parent widget for dialog.
        dir_path: Directory to process (optional).
    
    Returns:
        Tuple: (duplicates_fixed, files_modified, log_success)
    """
    if not dir_path:
        dir_path = QFileDialog.getExistingDirectory(parent, "Select Directory", "")
        if not dir_path:
            return 0, 0, False

    if not os.path.isdir(dir_path):
        return 0, 0, False

    # Test writability of parent directory
    parent_dir = os.path.dirname(dir_path)
    try:
        test_file = os.path.join(parent_dir, f"test_{time.time()}.tmp")
        with open(test_file, 'w') as f:
            f.write("test")
        os.remove(test_file)
    except (OSError, PermissionError):
        return 0, 0, False

    # Initialize log file in LegacyTextTuring
    legacy_dir = os.path.join(parent_dir, "LegacyTextTuring")
    log_file = os.path.join(legacy_dir, "Log.txt")
    log_success = True
    try:
        os.makedirs(legacy_dir, exist_ok=True)
        if not os.path.exists(legacy_dir):
            raise OSError(f"Failed to create {legacy_dir}")
    except (OSError, PermissionError):
        log_success = False
        return 0, 0, False

    # Collect .xml, .dita, and .ditamap files
    xml_files = []
    ditamap_files = []
    try:
        for root, _, files in os.walk(dir_path):
            if 'LegacyTextTuring' in root:
                continue
            for file in files:
                if file.endswith((".xml", ".dita")):
                    xml_files.append(os.path.abspath(os.path.join(root, file)).replace('\\', '/'))
        if os.path.exists(parent_dir) and 'LegacyTextTuring' not in parent_dir:
            for file in os.listdir(parent_dir):
                if file.endswith(".ditamap"):
                    ditamap_files.append(os.path.abspath(os.path.join(parent_dir, file)).replace('\\', '/'))
    except OSError:
        if log_success:
            try:
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"Error: Directory scan failed\n")
            except (OSError, PermissionError):
                pass
        return 0, 0, log_success

    # Collect IDs
    top_id_map = {}
    nested_id_map = {}
    for file_path in xml_files:
        try:
            tree = etree.parse(file_path)
            root = tree.getroot()
            top_id = root.get('id')
            if top_id:
                top_id_map.setdefault(top_id, []).append(file_path)
            for elem in tree.xpath("//*[@id]"):
                elem_id = elem.get('id')
                if elem_id != top_id:
                    nested_id_map.setdefault(elem_id, []).append((file_path, top_id or ''))
        except etree.LxmlError:
            continue

    # Process duplicates
    rename_map = {}
    modified_files = set()
    all_ids = set(top_id_map.keys()).union(nested_id_map.keys())
    duplicates_fixed = 0

    # Top-level ID duplicates
    for orig_id, file_paths in top_id_map.items():
        if len(file_paths) > 1:
            for idx, file_path in enumerate(file_paths[1:], 1):
                n = idx
                new_id = f"ttu_{orig_id}_{n}"
                while new_id in all_ids:
                    n += 1
                    new_id = f"ttu_{orig_id}_{n}"
                rename_map.setdefault(orig_id, {})[file_path] = new_id
                all_ids.add(new_id)
                modified_files.add(file_path)
                duplicates_fixed += 1

    # Nested ID duplicates
    for orig_id, entries in nested_id_map.items():
        by_parent = {}
        for file_path, parent_id in entries:
            by_parent.setdefault((file_path, parent_id), []).append(file_path)
        for (file_path, parent_id), paths in by_parent.items():
            if len(paths) > 1:
                for idx, _ in enumerate(paths[1:], 1):
                    n = idx
                    new_id = f"ttu_{orig_id}_{n}"
                    while new_id in all_ids:
                        n += 1
                        new_id = f"ttu_{orig_id}_{n}"
                    rename_map.setdefault(orig_id, {})[file_path] = new_id
                    all_ids.add(new_id)
                    modified_files.add(file_path)
                    duplicates_fixed += 1

    # Update files (IDs and internal references)
    files_modified = 0
    files_with_link_changes = set()
    for file_path in modified_files:
        try:
            tree = etree.parse(file_path)
            root = tree.getroot()
            modified = False

            orig_top_id = root.get('id')
            if orig_top_id in rename_map and file_path in rename_map[orig_top_id]:
                new_id = rename_map[orig_top_id][file_path]
                root.set('id', new_id)
                modified = True

            for elem in tree.xpath("//*[@id]"):
                elem_id = elem.get('id')
                if elem_id in rename_map and file_path in rename_map[elem_id]:
                    new_id = rename_map[elem_id][file_path]
                    elem.set('id', new_id)
                    modified = True

            for xref in tree.xpath("//xref[@href]"):
                href = xref.get('href')
                new_href = href
                if href.startswith('#'):
                    if '/' in href:
                        parts = href[1:].split('/', 1)
                        if len(parts) == 2:
                            top_id, nested_id = parts
                            if top_id == orig_top_id and orig_top_id in rename_map and file_path in rename_map[orig_top_id]:
                                new_href = f"#{rename_map[orig_top_id][file_path]}/{nested_id}"
                            if nested_id in rename_map and file_path in rename_map[nested_id]:
                                new_href = f"#{top_id if new_href == href else rename_map[orig_top_id][file_path]}/{rename_map[nested_id][file_path]}"
                    else:
                        href_id = href[1:]
                        if href_id in rename_map and file_path in rename_map[href_id]:
                            new_href = f"#{rename_map[href_id][file_path]}"
                if new_href != href:
                    xref.set('href', new_href)
                    files_with_link_changes.add(file_path)
                    modified = True

            if modified:
                if file_path in files_with_link_changes:
                    # Backup file to LegacyTextTuring with folder hierarchy
                    rel_path = os.path.relpath(file_path, parent_dir).replace('\\', '/')
                    backup_path = os.path.join(legacy_dir, rel_path)
                    if not os.path.exists(backup_path):
                        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                        shutil.copy2(file_path, backup_path)
                tree.write(file_path, encoding=tree.docinfo.encoding,
                         doctype=tree.docinfo.doctype, pretty_print=False,
                         xml_declaration=True)
                files_modified += 1

        except etree.LxmlError:
            continue
        except OSError:
            if log_success:
                try:
                    with open(log_file, 'a', encoding='utf-8') as f:
                        f.write(f"Error: File write failed {file_path}\n")
                except (OSError, PermissionError):
                    pass
            continue

    # Update cross-file references
    header_written = False
    for file_path in xml_files + ditamap_files:
        try:
            tree = etree.parse(file_path)
            modified = False
            for elem in tree.xpath("//xref[@href]|//topicref[@href]"):
                href = elem.get('href')
                new_href = href
                if '#' in href and not href.startswith('#'):
                    filename, ref_id = href.split('#', 1)
                    filename = unquote(filename)
                    abs_path = os.path.abspath(os.path.join(os.path.dirname(file_path), filename)).replace('\\', '/')
                    if abs_path in xml_files:
                        folder_name = os.path.basename(os.path.dirname(abs_path))
                        mod_folder = os.path.basename(os.path.dirname(file_path))
                        mod_file = os.path.basename(file_path)
                        if '/' in ref_id:
                            top_id, nested_id = ref_id.split('/', 1)
                            new_ref_id = ref_id
                            if top_id in rename_map and abs_path in rename_map[top_id]:
                                new_ref_id = f"{rename_map[top_id][abs_path]}/{nested_id}"
                            if nested_id in rename_map and abs_path in rename_map[nested_id]:
                                new_ref_id = f"{top_id if new_ref_id == ref_id else rename_map[top_id][abs_path]}/{rename_map[nested_id][abs_path]}"
                            if new_ref_id != ref_id:
                                new_href = f"{href.split('#', 1)[0]}#{new_ref_id}"
                        else:
                            if ref_id in rename_map and abs_path in rename_map[ref_id]:
                                new_ref_id = rename_map[ref_id][abs_path]
                                new_href = f"{href.split('#', 1)[0]}#{new_ref_id}"
                        if new_href != href:
                            elem.set('href', new_href)
                            files_with_link_changes.add(file_path)
                            modified = True

            if modified:
                # Backup file to LegacyTextTuring with folder hierarchy
                rel_path = os.path.relpath(file_path, parent_dir).replace('\\', '/')
                backup_path = os.path.join(legacy_dir, rel_path)
                if not os.path.exists(backup_path):
                    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                    shutil.copy2(file_path, backup_path)
                tree.write(file_path, encoding=tree.docinfo.encoding,
                         doctype=tree.docinfo.doctype, pretty_print=False,
                         xml_declaration=True)
                files_modified += 1
                # Log link changes with single header
                if log_success:
                    try:
                        with open(log_file, 'a', encoding='utf-8') as f:
                            if not header_written:
                                f.write(f"-----------------------------\nUpdated XMLs for Ensuring Unique IDs:\n")
                                header_written = True
                            f.write(f"{rel_path} - Updated ID\n")
                    except (OSError, PermissionError):
                        log_success = False

        except etree.LxmlError:
            continue
        except OSError:
            if log_success:
                try:
                    with open(log_file, 'a', encoding='utf-8') as f:
                        f.write(f"Error: File write failed {file_path}\n")
                except (OSError, PermissionError):
                    pass
            continue

    # Write summary
    if log_success:
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"Summary: Fixed {duplicates_fixed} duplicates in {files_modified} files\n")
        except (OSError, PermissionError):
            log_success = False

    return duplicates_fixed, files_modified, log_success