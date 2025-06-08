from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog, QTableWidget, QTableWidgetItem, QMenu, QApplication
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QFont, QBrush, QColor, QDesktopServices
from remove_duplicate_ids import remove_duplicate_ids
from fix_tables import validate_tables
from fix_graphics import validate_graphics
from validate_filename import validate_filename
from validate_chapter_toc import validate_chapter_toc, validate_subchapter_toc
import os
import re
from lxml import etree
from urllib.parse import unquote, quote
from pathlib import Path
import logging
from datetime import datetime
import tempfile
import uuid

# Set up logging to file only (no console output)
log_file = os.path.expanduser("~/Desktop/ftp_debug.log")
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.propagate = False
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

logging.getLogger('').handlers = []

try:
    file_handler = logging.FileHandler(log_file, mode='a')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
except Exception as e:
    fallback_log = os.path.join(tempfile.gettempdir(), "ftp_debug.log")
    file_handler = logging.FileHandler(fallback_log, mode='a')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.warning(f"Could not write to {log_file}. Using fallback log at {fallback_log}")

def is_empty_except_title(xml_path):
    """Check if an XML file contains only a title element and no other significant content."""
    try:
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(str(xml_path), parser)
        root = tree.getroot()
        
        # Get all child elements of the root
        children = [child for child in root if etree.iselement(child)]
        
        # Find title element
        title_elements = root.xpath("//title")
        
        # Check if there's exactly one title and no other significant content
        has_title = len(title_elements) == 1
        has_other_content = False
        
        # Check for other elements that might contain content
        for child in children:
            if child.tag != "title":
                if child.text and child.text.strip():
                    has_other_content = True
                    break
                if child.tail and child.tail.strip():
                    has_other_content = True
                    break
                if len(child) > 0:
                    has_other_content = True
                    break
        
        return has_title and not has_other_content
    except etree.LxmlError:
        logger.debug(f"Skipping malformed XML in is_empty_except_title: {xml_path}")
        return False
    except Exception as e:
        logger.debug(f"Error in is_empty_except_title for {xml_path}: {str(e)}")
        return False

def update_xml_file(xml_path, child_hrefs):
    """Update an XML file with a conbody containing xrefs to child hrefs, using existing conbody if present."""
    try:
        parser = etree.XMLParser(recover=True, remove_blank_text=True)
        tree = etree.parse(str(xml_path), parser)
        root = tree.getroot()
        
        # Preserve original title and root attributes
        title = root.find("title")
        if title is None:
            logger.error(f"No title found in {xml_path}")
            return False
        
        # Check for existing conbody
        conbody = root.find("conbody")
        if conbody is None:
            # Create new conbody if none exists
            conbody = etree.SubElement(root, "conbody")
        
        # Create paragraph and unordered list
        p = etree.SubElement(conbody, "p")
        p.text = "This chapter contains the following topics: "
        ul = etree.SubElement(p, "ul", id=f"ul_{uuid.uuid4().hex[:12]}")
        
        # Add xref for each child href
        for href in child_hrefs:
            li = etree.SubElement(ul, "li")
            xref = etree.SubElement(li, "xref", href=href)
        
        # Write updated XML back to file
        tree.write(str(xml_path), encoding="UTF-8", xml_declaration=True, doctype=root.getroottree().docinfo.doctype, pretty_print=True)
        logger.info(f"Successfully updated {xml_path} with conbody and xrefs")
        return True
    except etree.LxmlError as e:
        logger.error(f"XML parsing error in update_xml_file for {xml_path}: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Error in update_xml_file for {xml_path}: {str(e)}")
        return False

def validate_empty_headings(ditamap_path: str) -> list:
    """
    Validate XML files referenced in a DITA map for empty content except title.
    Returns files that have only a title and child topicrefs.
    
    Args:
        ditamap_path: Path to the DITA map file.
    
    Returns:
        list: List of tuples (file_name, folder_path, file_path, href) for files with empty headings.
    """
    results = []
    base_dir = Path(ditamap_path).parent
    try:
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(str(ditamap_path), parser)
        namespaces = {'dita': 'http://dita.oasis-open.org/architecture/2005/'}
        
        # Log all hrefs in the DITA map for debugging
        topicrefs = tree.xpath("//dita:topicref | //topicref | //dita:chapter | //chapter", namespaces=namespaces)
        all_hrefs = [tr.get("href") for tr in topicrefs if tr.get("href")]
        logger.debug(f"All hrefs in DITA map {ditamap_path}: {all_hrefs}")
        
        for topicref in topicrefs:
            href = topicref.get("href")
            if not href:
                logger.debug(f"Skipping topicref with no href in {ditamap_path}")
                continue
            
            # Decode URL-encoded href and normalize path
            decoded_href = unquote(href).replace('\\', '/')
            try:
                xml_path = (base_dir / decoded_href).resolve()
                if not xml_path.exists():
                    logger.debug(f"File not found: {xml_path}")
                    continue
                if xml_path.suffix.lower() not in ('.xml', '.dita'):
                    logger.debug(f"Skipping non-XML/DITA file: {xml_path}")
                    continue
                
                # Get child topicref hrefs (use filename only)
                child_hrefs = [child.get("href").split('/')[-1] for child in topicref.xpath("./dita:topicref | ./topicref", namespaces=namespaces) if child.get("href")]
                
                if is_empty_except_title(xml_path) and child_hrefs:
                    relative_path = xml_path.relative_to(base_dir)
                    folder_path = str(xml_path.parent)
                    file_name = xml_path.name
                    results.append((file_name, folder_path, str(xml_path), href))
                    logger.debug(f"Found empty heading file: {file_name}, folder: {folder_path}, href: {href}, child_hrefs: {child_hrefs}")
            except (ValueError, OSError) as e:
                logger.debug(f"Error processing href {href}: {str(e)}")
                continue
    except etree.LxmlError as e:
        logger.error(f"Error parsing DITA map {ditamap_path}: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in validate_empty_headings for {ditamap_path}: {str(e)}")
    logger.debug(f"validate_empty_headings found {len(results)} files")
    return results

class ValidateXMLsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.directory_path = ""
        self.ditamap_path = ""
        self.file_paths = []
        self.href_map = {}  # Map file paths to their hrefs
        self.current_mode = ""
        self.selected_row = None
        self.rename_results = []

        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        self.setLayout(layout)

        button_panel = QHBoxLayout()
        button_panel.setSpacing(8)
        button_panel.setContentsMargins(0, 0, 0, 10)

        self.remove_duplicate_ids_btn = QPushButton("Remove Duplicate IDs")
        self.validate_tables_btn = QPushButton("Validate Tables")
        self.validate_graphics_btn = QPushButton("Validate Graphics")
        self.validate_filename_btn = QPushButton("Validate File Name")
        self.validate_chapter_toc_btn = QPushButton("Validate Chapter TOC")
        self.fix_empty_headings_btn = QPushButton("Fix Empty Headings")
        for btn in [self.remove_duplicate_ids_btn, self.validate_tables_btn,
                    self.validate_graphics_btn, self.validate_filename_btn,
                    self.validate_chapter_toc_btn, self.fix_empty_headings_btn]:
            btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
            button_panel.addWidget(btn)
        layout.addLayout(button_panel)

        self.feedback_label = QLabel("Select a check to begin")
        self.feedback_label.setFont(QFont("Helvetica", 14, QFont.Weight.Bold))
        self.feedback_label.setStyleSheet("color: #FFFFFF;")
        self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.feedback_label)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Chapter Name", "Topic/SubTopic Title"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setFont(QFont("Helvetica", 10))
        self.table.setAlternatingRowColors(False)
        self.table.setWordWrap(True)
        self.table.setVisible(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.cellClicked.connect(self.handle_cell_click)
        self.table.setStyleSheet("QTableWidget::item { color: blue; text-decoration: underline; }")

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(30)

        layout.addWidget(self.table, stretch=1)

        bottom_panel = QHBoxLayout()
        bottom_panel.setSpacing(8)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))

        self.fix_all_btn = QPushButton("Fix All")
        self.fix_all_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.fix_all_btn.setVisible(False)
        self.fix_all_btn.clicked.connect(self.handle_fix_all)

        self.back_btn = QPushButton("Back to Menu")
        self.back_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))

        bottom_panel.addWidget(self.refresh_btn)
        bottom_panel.addWidget(self.fix_all_btn)
        bottom_panel.addWidget(self.back_btn)
        layout.addLayout(bottom_panel)

        self.setStyleSheet("""
            QWidget {
                background-color: #1F252A;
            }
            QPushButton {
                background-color: #0D6E6E;
                color: #FFFFFF;
                padding: 5px 10px;
                border-radius: 4px;
                border: 1px solid #0A5555;
                min-width: 60px;
                min-height: 24px;
            }
            QPushButton:hover {
                background-color: #139999;
                border: 1px solid #0C7A7A;
            }
            QPushButton:disabled {
                background-color: #666666;
                border: 1px solid #555555;
            }
            QTableWidget {
                background-color: #FFFFFF;
                color: #121416;
                border-radius: 4px;
                padding: 3px;
            }
            QTableWidget::item {
                background-color: #FFFFFF;
                padding: 2px;
                margin: 0px;
            }
            QTableWidget QLabel {
                background-color: #FFFFFF;
            }
        """)

        self.remove_duplicate_ids_btn.clicked.connect(self.handle_remove_duplicate_ids)
        self.validate_tables_btn.clicked.connect(self.handle_validate_tables)
        self.validate_graphics_btn.clicked.connect(self.handle_validate_graphics)
        self.validate_filename_btn.clicked.connect(self.handle_validate_filename)
        self.validate_chapter_toc_btn.clicked.connect(self.handle_validate_chapter_toc)
        self.fix_empty_headings_btn.clicked.connect(self.handle_fix_empty_headings)
        self.refresh_btn.clicked.connect(self.handle_refresh)
        self.back_btn.clicked.connect(self.parent_window.return_to_main_menu)

        # Debug button connections
        logger.debug("Button connections established in ValidateXMLsWidget.__init__")
        self.fix_empty_headings_btn.clicked.connect(lambda: logger.debug("Fix Empty Headings button clicked"))
        self.fix_all_btn.clicked.connect(lambda: logger.debug("Fix All button clicked"))

    def show_context_menu(self, pos):
        index = self.table.indexAt(pos)
        if not index.isValid() or index.column() != 0 or self.current_mode != "chapter_toc":
            return

        menu = QMenu(self)
        copy_action = menu.addAction("Copy File Name")
        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action == copy_action:
            row = index.row()
            file_path = self.file_paths[row]
            QApplication.clipboard().setText(file_path)
            logger.debug(f"Copied file name: {file_path}")
            self._flush_handlers()

            item = self.table.item(row, 0)
            if item:
                item.setBackground(QBrush(QColor("#FFA500")))
                QTimer.singleShot(1000, lambda: item.setBackground(QBrush(QColor("#FFFFFF"))))

    def _flush_handlers(self):
        for handler in logger.handlers:
            handler.flush()

    def handle_remove_duplicate_ids(self):
        self.directory_path = QFileDialog.getExistingDirectory(self, "Select Directory", "")
        if not self.directory_path:
            self.feedback_label.setText("No directory selected")
            return
        self.feedback_label.setText("Processing...")
        try:
            duplicates_fixed, files_modified = remove_duplicate_ids(self, self.directory_path)
            self.feedback_label.setText(f"Fixed {duplicates_fixed} duplicates in {files_modified} files")
        except Exception as e:
            self.feedback_label.setText(f"Error: {str(e)}")
            logger.debug(f"Error in Remove Duplicate IDs: {str(e)}")
        self._flush_handlers()

    def handle_validate_tables(self):
        self.directory_path = QFileDialog.getExistingDirectory(self, "Select Directory", "")
        if not self.directory_path:
            self.feedback_label.setText("No directory selected")
            return
        self.current_mode = "tables"
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["File", "Table Caption", "Table Width", "Fix"])
        self.fix_all_btn.setVisible(False)
        self.populate_table(validate_tables)

    def handle_validate_graphics(self):
        self.directory_path = QFileDialog.getExistingDirectory(self, "Select Directory", "")
        if not self.directory_path:
            self.feedback_label.setText("No directory selected")
            return
        self.current_mode = "graphics"
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["File", "Size Attributes", "Figure Title", "Fix"])
        self.fix_all_btn.setVisible(False)
        self.populate_table(validate_graphics)

    def handle_validate_filename(self):
        self.directory_path = QFileDialog.getExistingDirectory(self, "Select Directory", "")
        if not self.directory_path:
            self.feedback_label.setText("No directory selected")
            return
        self.current_mode = "filename"
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["File Name", "Topic Title", "Fix"])
        self.fix_all_btn.setVisible(True)
        self.populate_table(validate_filename)

    def handle_validate_chapter_toc(self):
        self.ditamap_path, _ = QFileDialog.getOpenFileName(
            self, "Select DITA Map", "", "DITA Map Files (*.ditamap);;All Files (*)"
        )
        if not self.ditamap_path:
            self.feedback_label.setText("No DITA map selected")
            return
        self.directory_path = str(Path(self.ditamap_path).parent)
        self.current_mode = "chapter_toc"
        self.table.setVisible(True)
        self.fix_all_btn.setVisible(False)
        self.populate_table_toc()

    def handle_fix_empty_headings(self):
        logger.debug("Entering handle_fix_empty_headings")
        self.ditamap_path, _ = QFileDialog.getOpenFileName(
            self, "Select DITA Map", "", "DITA Map Files (*.ditamap);;All Files (*)"
        )
        if not self.ditamap_path:
            self.feedback_label.setText("No DITA map selected")
            logger.debug("No DITA map selected")
            return
        self.directory_path = str(Path(self.ditamap_path).parent)
        self.current_mode = "empty_headings"
        self.table.setVisible(True)
        self.fix_all_btn.setVisible(True)
        self.populate_table_empty_headings()
        logger.debug("Completed handle_fix_empty_headings")

    def handle_fix_empty_heading(self, row):
        logger.debug(f"Entering handle_fix_empty_heading for row {row}")
        if self.current_mode != "empty_headings":
            self.feedback_label.setText("Fix only available in Fix Empty Headings mode")
            logger.warning("Fix attempted in non-empty_headings mode")
            return
        try:
            file_path = self.file_paths[row]
            href = self.href_map.get(file_path)
            logger.debug(f"Processing file: {file_path}, href: {href}")
            if not href:
                self.feedback_label.setText(f"No href found for {os.path.basename(file_path)}")
                logger.warning(f"No href found for {file_path}")
                return
            
            # Get child hrefs from DITA map for this file
            parser = etree.XMLParser(recover=True)
            tree = etree.parse(self.ditamap_path, parser)
            namespaces = {'dita': 'http://dita.oasis-open.org/architecture/2005/'}
            
            # Normalize href for matching
            decoded_href = unquote(href).replace('\\', '/')
            logger.debug(f"Looking for topicref with href: {decoded_href}")
            
            topicref = tree.xpath(
                f"//dita:topicref[@href='{href}' or @href='{decoded_href}'] | "
                f"//topicref[@href='{href}' or @href='{decoded_href}'] | "
                f"//dita:chapter[@href='{href}' or @href='{decoded_href}'] | "
                f"//chapter[@href='{href}' or @href='{decoded_href}']",
                namespaces=namespaces
            )
            
            if not topicref:
                self.feedback_label.setText(f"No topicref found for {os.path.basename(file_path)}")
                logger.warning(f"No topicref found for {file_path} with href {href} or {decoded_href}")
                return
            
            child_hrefs = [child.get("href").split('/')[-1] for child in topicref[0].xpath("./dita:topicref | ./topicref", namespaces=namespaces) if child.get("href")]
            logger.debug(f"Found child hrefs: {child_hrefs}")
            
            if not child_hrefs:
                self.feedback_label.setText(f"No child topics found for {os.path.basename(file_path)}")
                logger.warning(f"No child topicrefs found for {file_path}")
                return
            
            # Fix the file
            if update_xml_file(file_path, child_hrefs):
                # Open the file after fixing
                if not os.path.exists(file_path):
                    raise FileNotFoundError(f"The file {file_path} does not exist.")
                url = QUrl.fromLocalFile(file_path)
                QDesktopServices.openUrl(url)
                logger.debug(f"Opened file after fix: {file_path}")
                self.feedback_label.setText(f"Fixed and opened {os.path.basename(file_path)}")
                self.table.removeRow(row)
                self.file_paths.pop(row)
                del self.href_map[file_path]
            else:
                self.feedback_label.setText(f"Failed to fix {os.path.basename(file_path)}")
                logger.error(f"Failed to fix empty heading for {file_path}")
        except Exception as e:
            self.feedback_label.setText(f"Error fixing file: {str(e)}")
            logger.error(f"Error fixing file {file_path}: {str(e)}")
        self._flush_handlers()
        logger.debug("Completed handle_fix_empty_heading")

    def handle_fix_all(self):
        logger.debug("Entering handle_fix_all")
        if self.current_mode == "filename":
            self.handle_fix_all_filename()
        elif self.current_mode == "empty_headings":
            self.handle_fix_all_empty_headings()
        else:
            self.feedback_label.setText("Fix All only available in File Name or Fix Empty Headings mode")
            logger.warning(f"Fix All attempted in mode: {self.current_mode}")
        self._flush_handlers()

    def handle_fix_all_empty_headings(self):
        logger.debug("Entering handle_fix_all_empty_headings")
        if self.current_mode != "empty_headings":
            self.feedback_label.setText("Fix All only available in Fix Empty Headings mode")
            logger.warning("Fix All attempted in non-empty_headings mode")
            return
        total_files = self.table.rowCount()
        if total_files == 0:
            self.feedback_label.setText("No files to fix")
            logger.info("No files to fix in Fix All Empty Headings")
            return
        logger.info("=== Starting Fix All Empty Headings ===")
        success_count = 0
        failed_count = 0
        try:
            parser = etree.XMLParser(recover=True)
            tree = etree.parse(self.ditamap_path, parser)
            namespaces = {'dita': 'http://dita.oasis-open.org/architecture/2005/'}
            
            for row in range(total_files - 1, -1, -1):
                file_path = self.file_paths[row]
                href = self.href_map.get(file_path)
                logger.debug(f"Processing file {file_path} for Fix All, href: {href}")
                if not href:
                    logger.warning(f"No href found for {file_path}")
                    failed_count += 1
                    self.feedback_label.setText(f"Skipped {os.path.basename(file_path)}: No href found")
                    continue
                
                try:
                    # Get child hrefs for this file
                    decoded_href = unquote(href).replace('\\', '/')
                    logger.debug(f"Looking for topicref with href: {decoded_href}")
                    
                    topicref = tree.xpath(
                        f"//dita:topicref[@href='{href}' or @href='{decoded_href}'] | "
                        f"//topicref[@href='{href}' or @href='{decoded_href}'] | "
                        f"//dita:chapter[@href='{href}' or @href='{decoded_href}'] | "
                        f"//chapter[@href='{href}' or @href='{decoded_href}']",
                        namespaces=namespaces
                    )
                    
                    if not topicref:
                        logger.warning(f"No topicref found for {file_path} with href {href} or {decoded_href}")
                        failed_count += 1
                        self.feedback_label.setText(f"Skipped {os.path.basename(file_path)}: No topicref found")
                        continue
                    
                    child_hrefs = [child.get("href").split('/')[-1] for child in topicref[0].xpath("./dita:topicref | ./topicref", namespaces=namespaces) if child.get("href")]
                    logger.debug(f"Found child hrefs: {child_hrefs}")
                    
                    if not child_hrefs:
                        logger.warning(f"No child topicrefs found for {file_path}")
                        failed_count += 1
                        self.feedback_label.setText(f"Skipped {os.path.basename(file_path)}: No child topics")
                        continue
                    
                    # Fix the file
                    if update_xml_file(file_path, child_hrefs):
                        success_count += 1
                        self.table.removeRow(row)
                        self.file_paths.pop(row)
                        del self.href_map[file_path]
                        logger.debug(f"Successfully fixed empty heading for {file_path}")
                        self.feedback_label.setText(f"Fixed {os.path.basename(file_path)}")
                    else:
                        failed_count += 1
                        logger.error(f"Failed to fix empty heading for {file_path}")
                        self.feedback_label.setText(f"Failed to fix {os.path.basename(file_path)}")
                except Exception as e:
                    failed_count += 1
                    logger.error(f"Error fixing file {file_path}: {str(e)}")
                    self.feedback_label.setText(f"Error fixing {os.path.basename(file_path)}: {str(e)}")
        except Exception as e:
            logger.error(f"Error parsing DITA map for Fix All: {str(e)}")
            self.feedback_label.setText(f"Error during Fix All: {str(e)}")
            return
        
        message = f"Fixed {success_count} files"
        if failed_count > 0:
            message += f", {failed_count} failures"
        self.feedback_label.setText(message)
        logger.info(f"Fix All Empty Headings completed: {message}")
        self._flush_handlers()
        logger.debug("Completed handle_fix_all_empty_headings")

    def handle_fix_all_filename(self):
        logger.debug("Entering handle_fix_all_filename")
        if self.current_mode != "filename":
            self.feedback_label.setText("Fix All only available in File Name mode")
            logger.warning("Fix All attempted in non-filename mode")
            self._flush_handlers()
            return
        if not self.ditamap_path:
            parent_dir = os.path.dirname(self.directory_path)
            ditamap_files = [f for f in os.listdir(parent_dir) if f.endswith(".ditamap")]
            if len(ditamap_files) == 1:
                self.ditamap_path = os.path.join(parent_dir, ditamap_files[0])
                logger.info(f"Auto-detected DITA map: {self.ditamap_path}")
            elif len(ditamap_files) > 1:
                self.feedback_label.setText("Multiple DITA maps found in parent directory.")
                logger.error("Multiple DITA maps found in parent directory")
                self._flush_handlers()
                return
            else:
                self.feedback_label.setText("No DITA map found in parent directory.")
                logger.error("No DITA map found in parent directory")
                self._flush_handlers()
                return
        total_files = self.table.rowCount()
        if total_files == 0:
            self.feedback_label.setText("No files to fix. Check validate_filename output.")
            logger.info("No files to fix in Fix All")
            self._flush_handlers()
            return
        logger.info("=== Starting Fix All Filename ===")
        success_count = 0
        total_ref_success = 0
        self.rename_results = []
        failed_rows = []
        invalid_hrefs = []
        new_file_paths = []
        rename_map = {}
        rename_tracker = {}
        ditamap_hrefs, missing_hrefs = self.build_ditamap_hrefs()
        logger.info("Checking case mismatches before renaming")
        for href, rel_href, abs_href in ditamap_hrefs:
            if os.path.exists(abs_href):
                fs_base = os.path.basename(abs_href)
                href_base = os.path.basename(unquote(href.split('#')[0]))
                if fs_base != href_base:
                    logger.warning(f"Case mismatch detected: Filesystem {fs_base} vs DITAmap {href_base}")
                    old_path = abs_href
                    new_filename = href_base
                    new_path = os.path.join(os.path.dirname(old_path), new_filename)
                    if old_path != new_path:
                        try:
                            os.rename(old_path, new_path)
                            logger.info(f"Renamed for case correction: {old_path} -> {new_path}")
                            normalized_href = unquote(href.split('#')[0])
                            if normalized_href.startswith('Topics/Topics/'):
                                normalized_href = normalized_href.replace('Topics/Topics/', '')
                            rename_map[abs_href] = new_filename
                            chapter = os.path.basename(os.path.dirname(old_path))
                            rename_tracker.setdefault(chapter, {})[abs_href] = new_filename
                            logger.debug(f"Added to rename_tracker: {chapter} -> {abs_href}: {new_filename}")
                            success_count += 1
                            self.rename_results.append((fs_base, new_filename))
                            new_file_paths.append(new_path)
                        except OSError as e:
                            logger.error(f"Failed to rename for case: {old_path} -> {new_path}: {str(e)}")
                            failed_rows.append((rel_href, str(e)))
        for row in range(total_files - 1, -1, -1):
            logger.debug(f"Processing row {row}, file: {self.file_paths[row]}")
            success, result, original_path, new_filename = self.rename_file(row, ditamap_hrefs, rename_tracker)
            if success:
                success_count += 1
                original_filename, new_filename = result
                self.rename_results.append((original_filename, new_filename))
                new_file_paths.append(os.path.join(os.path.dirname(self.file_paths[row]), new_filename))
                if original_path != os.path.join(os.path.dirname(original_path), new_filename):
                    rename_map[original_path] = new_filename
                self.table.removeRow(row)
                logger.debug(f"Successfully renamed row {row}: {original_filename} -> {new_filename}")
            else:
                failed_rows.append((row, result))
                logger.debug(f"Failed to rename row {row}: {result}")
        logger.info(f"Renamed {success_count} files")
        ref_success_count, errors, ditamap_count = self.update_xref_references(rename_tracker, rename_map)
        total_ref_success += ref_success_count
        logger.info("Validating hrefs in all files")
        for root, _, files in os.walk(self.directory_path):
            for file in files:
                if file.endswith((".xml", ".ditamap")):
                    file_path = os.path.join(root, file)
                    try:
                        tree = etree.parse(file_path)
                        for element in tree.xpath("//*[self::chapter or self::topicref or self::xref or self::appendix][@href]"):
                            href = unquote(element.get("href").split('#')[0])
                            if href.startswith(('http://', 'https://', 'mailto:')):
                                continue
                            href_norm = os.path.normpath(href).replace('\\', '/')
                            full_href_path = os.path.join(self.directory_path, href_norm)
                            file_dir = os.path.dirname(file_path)
                            resolved_href = os.path.normpath(os.path.join(file_dir, href)).replace('\\', '/')
                            if not os.path.exists(full_href_path) and resolved_href not in new_file_paths:
                                invalid_hrefs.append(f"Invalid href in {file_path}: {href}")
                                logger.warning(f"Invalid href in {file_path}: {href}")
                    except Exception as e:
                        logger.error(f"Error validating hrefs in {file_path}: {str(e)}")
        self._flush_handlers()
        message_parts = []
        if success_count > 0:
            message_parts.append(f"Renamed {success_count} files")
        if total_ref_success > 0:
            message_parts.append(f"Fixed {total_ref_success} references")
        if failed_rows:
            message_parts.append(f"{len(failed_rows)} rename failures")
        if invalid_hrefs:
            message_parts.append(f"{len(invalid_hrefs)} invalid hrefs")
        if missing_hrefs:
            message_parts.append(f"{len(missing_hrefs)} missing ditamap hrefs")
        message = ", ".join(message_parts) or "No changes made"
        self.feedback_label.setText(message)
        logger.info(f"Fix All completed: {message}")
        logger.info(f"Invalid hrefs found: {len(invalid_hrefs)}")
        for ih in invalid_hrefs:
            logger.warning(f"  {ih}")
        self._flush_handlers()
        if success_count > 0 or total_ref_success > 0:
            self.table.setColumnCount(2)
            self.table.setHorizontalHeaderLabels(["Before", "After File Names"])
            header = self.table.horizontalHeader()
            header.setSectionResizeMode(0, header.ResizeMode.Stretch)
            header.setSectionResizeMode(1, header.ResizeMode.Stretch)
            self.table.setRowCount(len(self.rename_results))
            for row, (before, after) in enumerate(self.rename_results):
                self.table.setItem(row, 0, QTableWidgetItem(before))
                self.table.setItem(row, 1, QTableWidgetItem(after))
            self.table.viewport().update()
        self.fix_all_btn.setEnabled(False)
        self.selected_row = None
        logger.debug("Completed handle_fix_all_filename")

    def handle_open_file(self, row):
        logger.debug(f"Entering handle_open_file for row {row}")
        try:
            file_path = self.file_paths[row]
            logger.debug(f"Opening file: {file_path}")
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"The file {file_path} does not exist.")
            url = QUrl.fromLocalFile(file_path)
            QDesktopServices.openUrl(url)
            logger.debug(f"Opened file: {file_path}")
            self.feedback_label.setText(f"Opened {os.path.basename(file_path)}")
        except Exception as e:
            self.feedback_label.setText(f"Error opening file: {str(e)}")
            logger.error(f"Error opening file {file_path}: {str(e)}")
        self._flush_handlers()
        logger.debug("Completed handle_open_file")

    def handle_row_selection(self):
        logger.debug("Entering handle_row_selection")
        if self.current_mode != "filename":
            return
        selection = self.table.selectionModel().selectedRows()
        if selection:
            self.selected_row = selection[0].row()
            self.fix_all_btn.setEnabled(True)
            logger.debug(f"Row selected: {self.selected_row}")
        else:
            self.selected_row = None
            self.fix_all_btn.setEnabled(False)
            logger.debug("No row selected")
        self._flush_handlers()

    def sanitize_filename(self, filename: str, original_filename: str = None, ditamap_href: str = None) -> str:
        logger.debug(f"Sanitizing filename: {filename}, original: {original_filename}, ditamap_href: {ditamap_href}")
        invalid_chars = r'[\\/:*?"<>|]'
        filename = re.sub(invalid_chars, ' ', filename)
        special_chars = r'[^a-zA-Z0-9\s\-_.]'
        filename = re.sub(special_chars, ' ', filename)
        filename = re.sub(r'\s+', ' ', filename).strip()
        if not filename:
            filename = "Untitled"
        logger.debug(f"Sanitized filename: {filename}")
        self._flush_handlers()
        return filename

    def build_ditamap_hrefs(self):
        logger.debug("Entering build_ditamap_hrefs")
        hrefs = []
        missing_hrefs = []
        title_map = {}
        if not self.ditamap_path:
            logger.warning("No ditamap path provided for href extraction")
            self._flush_handlers()
            return hrefs, missing_hrefs
        try:
            tree = etree.parse(self.ditamap_path)
            elements = tree.xpath("//*[self::chapter or self::topicref or self::xref or self::appendix][@href]")
            ditamap_dir = os.path.dirname(self.ditamap_path)
            for element in elements:
                href = element.get("href")
                if not href or href.startswith(('http://', 'https://', 'mailto:')):
                    continue
                decoded_href = unquote(href)
                if decoded_href.startswith('Topics/Topics/'):
                    decoded_href = decoded_href.replace('Topics/Topics/', '')
                    logger.warning(f"Normalized redundant Topics/ in href: {href} -> {decoded_href}")
                abs_href = os.path.normpath(os.path.join(ditamap_dir, decoded_href.split('#')[0])).replace('\\', '/')
                rel_href = os.path.relpath(abs_href, ditamap_dir).replace('\\', '/')
                if os.path.exists(abs_href):
                    try:
                        file_tree = etree.parse(abs_href)
                        title_elem = file_tree.xpath("//title")
                        title = title_elem[0].text.strip() if title_elem and title_elem[0].text else os.path.splitext(os.path.basename(abs_href))[0]
                        if title in title_map:
                            logger.warning(f"Duplicate title '{title}' found in {abs_href}, also in {title_map[title]}")
                        else:
                            title_map[title] = abs_href
                    except Exception as e:
                        logger.warning(f"Failed to parse file for title: {abs_href}, {str(e)}")
                    hrefs.append((href, rel_href, abs_href))
                else:
                    missing_hrefs.append(href)
                    logger.warning(f"Missing href in {self.ditamap_path}: {href} (resolved: {abs_href})")
        except Exception as e:
            logger.error(f"Failed to parse ditamap: {self.ditamap_path}: {str(e)}")
        self._flush_handlers()
        logger.debug(f"build_ditamap_hrefs returning {len(hrefs)} hrefs, {len(missing_hrefs)} missing")
        return hrefs, missing_hrefs

    def update_sectional_bookmarks(self, file_path, rename_tracker, rename_map, ditamap_dir, is_ditamap=False):
        logger.debug(f"Entering update_sectional_bookmarks for {file_path}")
        try:
            tree = etree.parse(file_path)
            modified = False
            elements = tree.xpath("//*[self::xref][@href]")
            file_dir = os.path.dirname(file_path)
            logger.info(f"Processing sectional bookmarks in file: {file_path} {'(DITA map)' if is_ditamap else ''}")
            for element in elements:
                href = element.get("href")
                if not href or href.startswith(('http://', 'https://', 'mailto:')):
                    continue
                href_parts = href.split('#')
                if len(href_parts) <= 1:
                    continue
                file_href = href_parts[0]
                fragment = f"#{href_parts[1]}"
                decoded_href = unquote(file_href).replace('\\', '/')
                abs_href = os.path.normpath(os.path.join(file_dir, decoded_href)).replace('\\', '/')
                matched = False
                
                for chapter, mappings in rename_tracker.items():
                    for original_abs_path, new_filename in mappings.items():
                        original_abs_path_norm = original_abs_path.replace('\\', '/')
                        if abs_href == original_abs_path_norm and new_filename != os.path.basename(original_abs_path_norm):
                            new_href = os.path.join(os.path.dirname(decoded_href), new_filename)
                            logger.info(f"Updated sectional xref in {file_path}: {href} -> {quote(new_href, safe='/') + fragment}")
                            element.set("href", quote(new_href, safe='/') + fragment)
                            matched = True
                            modified = True
                
                if not matched:
                    for original_abs_path, new_filename in rename_map.items():
                        original_abs_path_norm = original_abs_path.replace('\\', '/')
                        if abs_href == original_abs_path_norm and new_filename != os.path.basename(original_abs_path_norm):
                            new_href = os.path.join(os.path.dirname(decoded_href), new_filename)
                            logger.info(f"Updated sectional xref in {file_path}: {href} -> {quote(new_href, safe='/') + fragment}")
                            element.set("href", quote(new_href, safe='/') + fragment)
                            matched = True
                            modified = True
                
                if not matched:
                    logger.debug(f"Unmatched sectional xref in {file_path}: {href}")
            
            if modified:
                tree.write(file_path, encoding=tree.docinfo.encoding,
                         doctype=tree.docinfo.doctype, pretty_print=False,
                         xml_declaration=True)
                logger.info(f"Saved updated file with sectional bookmarks: {file_path}")
            self._flush_handlers()
            logger.debug("Completed update_sectional_bookmarks")
            return modified
        except Exception as e:
            logger.error(f"Failed to update sectional bookmarks in {file_path}: {str(e)}")
            self._flush_handlers()
            return False

    def update_ditamap_topicrefs(self, ditamap_path, rename_tracker, rename_map):
        logger.debug(f"Entering update_ditamap_topicrefs for {ditamap_path}")
        try:
            tree = etree.parse(ditamap_path)
            modified = False
            elements = tree.xpath("//*[self::topicref][@href]")
            ditamap_dir = os.path.dirname(ditamap_path)
            logger.info(f"Processing topicrefs in DITA map: {ditamap_path}")
            for element in elements:
                href = element.get("href")
                if not href or href.startswith(('http://', 'https://', 'mailto:')):
                    continue
                decoded_href = unquote(href).replace('\\', '/')
                abs_href = os.path.normpath(os.path.join(ditamap_dir, decoded_href.split('#')[0])).replace('\\', '/')
                path_parts = decoded_href.rsplit('/', 1)
                if len(path_parts) < 2:
                    logger.warning(f"Invalid href format in {ditamap_path}: {href}")
                    continue
                dir_path, filename = path_parts
                matched = False
                
                for chapter, mappings in rename_tracker.items():
                    for original_abs_path, new_filename in mappings.items():
                        original_abs_path_norm = original_abs_path.replace('\\', '/')
                        if abs_href == original_abs_path_norm and new_filename != os.path.basename(original_abs_path_norm):
                            new_href = f"{dir_path}/{new_filename}"
                            logger.info(f"Updated topicref in {ditamap_path}: {href} -> {new_href}")
                            element.set("href", new_href)
                            matched = True
                            modified = True
                
                if not matched:
                    for original_abs_path, new_filename in rename_map.items():
                        original_abs_path_norm = original_abs_path.replace('\\', '/')
                        if abs_href == original_abs_path_norm and new_filename != os.path.basename(original_abs_path_norm):
                            new_href = f"{dir_path}/{new_filename}"
                            logger.info(f"Updated topicref in {ditamap_path}: {href} -> {new_href}")
                            element.set("href", new_href)
                            matched = True
                            modified = True
                
                if not matched:
                    logger.debug(f"Unmatched topicref in {ditamap_path}: {href}")
            
            if modified:
                tree.write(ditamap_path, encoding=tree.docinfo.encoding,
                         doctype=tree.docinfo.doctype, pretty_print=False,
                         xml_declaration=True)
                logger.info(f"Saved updated DITA map: {ditamap_path}")
            self._flush_handlers()
            logger.debug("Completed update_ditamap_topicrefs")
            return modified
        except Exception as e:
            logger.error(f"Failed to update topicrefs in {ditamap_path}: {str(e)}")
            self._flush_handlers()
            return False

    def update_xref_references(self, rename_tracker: dict, rename_map: dict):
        logger.debug("Entering update_xref_references")
        success_count = 0
        error_messages = []
        modified_files = []
        unmatched_hrefs = []
        case_warnings = []
        ditamap_dir = os.path.dirname(self.ditamap_path) if self.ditamap_path else os.path.dirname(self.directory_path)
        logger.info(f"DITA map directory: {ditamap_dir}")

        def update_file(file_path, is_ditamap=False):
            nonlocal success_count, modified_files, unmatched_hrefs, case_warnings
            try:
                tree = etree.parse(file_path)
                modified = False
                elements = tree.xpath("//*[self::chapter or self::topicref or self::xref or self::appendix][@href]")
                file_dir = os.path.dirname(file_path)
                logger.info(f"Processing file: {file_path} {'(DITA map)' if is_ditamap else ''}")
                for element in elements:
                    href = element.get("href")
                    if not href or href.startswith(('http://', 'https://', 'mailto:')):
                        continue
                    href_parts = href.split('#')
                    file_href = href_parts[0]
                    fragment = f"#{href_parts[1]}" if len(href_parts) > 1 else ""
                    if fragment:
                        continue
                    decoded_href = unquote(file_href).replace('\\', '/')
                    abs_href = os.path.normpath(os.path.join(file_dir, decoded_href)).replace('\\', '/')
                    if not os.path.exists(abs_href):
                        logger.warning(f"File does not exist for href in {file_path}: {abs_href}")
                    rel_href = os.path.relpath(abs_href, ditamap_dir).replace('\\', '/')
                    new_href = decoded_href
                    matched = False
                    
                    for chapter, mappings in rename_tracker.items():
                        for original_abs_path, new_filename in mappings.items():
                            original_abs_path_norm = original_abs_path.replace('\\', '/')
                            if abs_href == original_abs_path_norm and new_filename != os.path.basename(original_abs_path_norm):
                                new_href = os.path.join(os.path.dirname(decoded_href), new_filename)
                                logger.info(f"Updated href in {file_path}: {href} -> {quote(new_href, safe='/')}")
                                element.set("href", quote(new_href, safe='/'))
                                matched = True
                                modified = True
                    
                    if not matched:
                        for original_abs_path, new_filename in rename_map.items():
                            original_abs_path_norm = original_abs_path.replace('\\', '/')
                            if abs_href == original_abs_path_norm and new_filename != os.path.basename(original_abs_path_norm):
                                new_href = os.path.join(os.path.dirname(decoded_href), new_filename)
                                logger.info(f"Updated href in {file_path}: {href} -> {quote(new_href, safe='/')}")
                                element.set("href", quote(new_href, safe='/'))
                                matched = True
                                modified = True
                            elif rel_href == os.path.relpath(original_abs_path_norm, ditamap_dir).replace('\\', '/'):
                                new_href = os.path.join(os.path.dirname(rel_href), new_filename)
                                logger.info(f"Updated href in {file_path}: {href} -> {quote(new_href, safe='/')}")
                                element.set("href", quote(new_href, safe='/'))
                                matched = True
                                modified = True
                            if not matched and len(unmatched_hrefs) < 100:
                                unmatched_hrefs.append(f"Unmatched href in {file_path}: {href}")
                    
                    if os.path.exists(abs_href) and os.path.basename(abs_href) != os.path.basename(unquote(new_href)):
                        case_warnings.append(f"Case mismatch in {file_path}: {os.path.basename(abs_href)} vs {os.path.basename(unquote(new_href))}")
                        logger.warning(f"Case mismatch in {file_path}: {os.path.basename(abs_href)} vs {os.path.basename(unquote(new_href))}")
                
                if modified:
                    modified_files.append(file_path)
                    tree.write(file_path, encoding=tree.docinfo.encoding,
                             doctype=tree.docinfo.doctype, pretty_print=False,
                             xml_declaration=True)
                    logger.info(f"Saved updated file: {file_path}")
                    success_count += 1
                self._flush_handlers()
            except Exception as e:
                error_messages.append(f"Failed to parse file: {os.path.basename(file_path)}: {str(e)}")
                logger.error(f"Failed to parse file: {file_path}: {str(e)}")
            except OSError as e:
                error_messages.append(f"Failed to update file {os.path.basename(file_path)}: {str(e)}")
                logger.error(f"Failed to update file: {file_path}: {str(e)}")
            self._flush_handlers()

        logger.info(f"Processing XML files in directory and subdirectories: {self.directory_path}")
        for root, _, files in os.walk(self.directory_path):
            for file in files:
                if file.endswith(".xml") and "LegacyTextTuring" not in root:
                    file_path = os.path.join(root, file)
                    update_file(file_path, is_ditamap=False)
                    self.update_sectional_bookmarks(file_path, rename_tracker, rename_map, ditamap_dir, is_ditamap=False)
        logger.info("Processing DITA map files in parent directory")
        try:
            parent_dir = os.path.dirname(self.directory_path)
            if not os.path.exists(parent_dir):
                error_messages.append(f"Parent directory not found: {parent_dir}")
                logger.error(f"Parent directory not found: {parent_dir}")
            else:
                ditamap_files = [f for f in os.listdir(parent_dir) if f.endswith(".ditamap")]
                if not ditamap_files:
                    error_messages.append("No .ditamap files found in parent directory")
                    logger.warning("No .ditamap files found in parent directory")
                for file in ditamap_files:
                    file_path = os.path.join(parent_dir, file)
                    if os.path.isfile(file_path):
                        update_file(file_path, is_ditamap=True)
                        self.update_sectional_bookmarks(file_path, rename_tracker, rename_map, ditamap_dir, is_ditamap=True)
                        self.update_ditamap_topicrefs(file_path, rename_tracker, rename_map)
        except Exception as e:
            error_messages.append(f"Error accessing parent directory: {str(e)}")
            logger.error(f"Error accessing parent directory: {str(e)}")
        self._flush_handlers()
        logger.info("=== Reference Update Summary ===")
        logger.info(f"Updated {success_count} references across {len(modified_files)} files")
        if unmatched_hrefs:
            logger.warning(f"Found {len(unmatched_hrefs)} unmatched hrefs (limited log)")
        if error_messages:
            logger.error(f"Encountered {len(error_messages)} errors")
        if case_warnings:
            logger.warning(f"Found {len(case_warnings)} case sensitivity warnings")
        self._flush_handlers()
        logger.debug("Completed update_xref_references")
        return success_count, error_messages, len(ditamap_files)

    def rename_file(self, row, ditamap_hrefs=None, rename_tracker=None):
        logger.debug(f"Renaming file at row {row}")
        try:
            original_path = self.file_paths[row]
            original_filename = os.path.basename(original_path)
            if not os.path.exists(original_path):
                error_msg = f("File does not exist: {original_path}")
                logger.error(error_msg)
                self._flush_handlers()
                return False, error_msg, original_path, None
            tree = etree.parse(original_path)
            title_elements = tree.xpath("//title")
            if not title_elements:
                error_msg = f("No <title> element found in {original_path}")
                logger.error(error_msg)
                self._flush_handlers()
                return False, error_msg, original_path, None
            title = title_elements[0].text.strip() if title_elements[0].text else os.path.splitext(original_filename)[0]
            new_filename = self.sanitize_filename(title) + ".xml"
            directory = os.path.dirname(original_path)
            new_path = os.path.join(directory, new_filename)
            logger.info(f"Renaming file: Original Path={original_path}, Title={title}, New Filename={new_filename}, New Path={new_path}")
            if os.path.exists(new_path) and new_path != original_path:
                base_name, ext = os.path.splitext(new_filename)
                counter = 1
                while os.path.exists(new_path):
                    new_filename = f"{base_name}_{counter}{ext}"
                    new_path = os.path.join(directory, new_filename)
                    counter += 1
                logger.debug(f"Filename conflict resolved: {new_filename}, new path: {new_path}")
            if new_path != original_path:
                try:
                    os.rename(original_path, new_path)
                    logger.info(f"Successfully renamed: {original_path} -> {new_path}")
                    if rename_tracker is not None:
                        chapter = os.path.basename(directory)
                        rename_tracker.setdefault(chapter, {})[original_path] = new_filename
                        logger.debug(f"Added to rename_tracker: {chapter} -> {original_path}: {new_filename}")
                except OSError as e:
                    error_msg = f("Failed to rename file: {original_path} -> {new_path}: {str(e)}")
                    logger.error(error_msg)
                    self._flush_handlers()
                    return False, error_msg, original_path, None
            else:
                logger.debug(f"No rename needed, paths identical: {original_path}")
                if rename_tracker is not None:
                    chapter = os.path.basename(directory)
                    rename_tracker.setdefault(chapter, {})[original_path] = original_filename
                    logger.debug(f"Added to rename_tracker (no change): {chapter} -> {original_path}: {original_filename}")
            self._flush_handlers()
            logger.debug("Completed rename_file")
            return True, (original_filename, new_filename), original_path, new_filename
        except Exception as e:
            error_msg = f("Error renaming file: {original_path}, {str(e)}")
            logger.error(error_msg)
            self._flush_handlers()
            return False, error_msg, original_path, None

    def handle_cell_click(self, row, column):
        logger.debug(f"Cell clicked: row={row}, column={column}")
        if row < 0 or row >= len(self.file_paths):
            logger.debug(f"Invalid row clicked: {row}, file_paths_length={len(self.file_paths)}")
            return
        # Handle clicks for chapter_toc mode
        if self.current_mode == "chapter_toc" and column == 1:
            # Check if row is a header row
            item = self.table.item(row, 0)
            if item and item.text() in ["Missing Chapter TOC", "Missing SubChapter TOC"]:
                logger.debug(f"Clicked header row {row}: {item.text()}")
                return
            # Adjust row to map to file_paths
            data_row = row
            for i in range(row):
                if self.table.item(i, 0) and self.table.item(i, 0).text() in ["Missing Chapter TOC", "Missing SubChapter TOC"]:
                    data_row -= 1
            if data_row < 0 or data_row >= len(self.file_paths):
                logger.debug(f"Invalid data_row {data_row} for row {row}, file_paths_length={len(self.file_paths)}")
                return
            file_path = self.file_paths[data_row]
            logger.debug(f"Hyperlink clicked for row {row}, data_row {data_row}, opening file: {file_path}")
            try:
                if not os.path.exists(file_path):
                    raise FileNotFoundError(f"The file {file_path} does not exist.")
                url = QUrl.fromLocalFile(file_path)
                QDesktopServices.openUrl(url)
                logger.debug(f"Opened file via hyperlink: {file_path}")
            except Exception as e:
                self.feedback_label.setText(f"Error opening file: {str(e)}")
                logger.error(f"Error opening file: {str(e)}")
        # Handle clicks for empty_headings mode (Folder Path column)
        elif self.current_mode == "empty_headings" and column == 1:
            folder_path = self.table.item(row, 1).text()
            logger.debug(f"Folder path clicked for row {row}: {folder_path}")
            try:
                if not os.path.exists(folder_path):
                    raise FileNotFoundError(f"The folder {folder_path} does not exist.")
                url = QUrl.fromLocalFile(folder_path)
                QDesktopServices.openUrl(url)
                logger.debug(f"Opened folder: {folder_path}")
            except Exception as e:
                self.feedback_label.setText(f"Error opening folder: {str(e)}")
                logger.error(f"Error opening folder: {str(e)}")
        self._flush_handlers()
        logger.debug("Completed handle_cell_click")

    def populate_table(self, validation_func):
        logger.debug("Entering populate_table")
        self.feedback_label.setVisible(False)
        self.table.setVisible(True)
        self.table.setRowCount(0)
        self.file_paths = []
        self.selected_row = None
        table_data = validation_func(self.directory_path)
        logger.debug(f"Validation data: {table_data}")
        if not table_data:
            self.feedback_label.setText("No issues found")
            self.feedback_label.setVisible(True)
            self.table.setVisible(False)
            logger.info("No issues found")
            self._flush_handlers()
            return
        if self.current_mode == "tables" or self.current_mode == "graphics":
            self.table.setColumnCount(4)
            if self.current_mode == "tables":
                self.table.setHorizontalHeaderLabels(["File", "Table Caption", "Table Width", "Fix"])
            else:
                self.table.setHorizontalHeaderLabels(["File", "Size Attributes", "Figure Title", "Fix"])
        elif self.current_mode == "filename":
            self.table.setColumnCount(3)
            self.table.setHorizontalHeaderLabels(["File Name", "Topic Title", "Fix"])
        for row, data in enumerate(table_data):
            if self.current_mode == "tables":
                relative_path, table_caption, width_issue = data
                full_file_path = os.path.join(self.directory_path, relative_path)
            elif self.current_mode in ("graphics", "filename"):
                if self.current_mode == "graphics":
                    relative_path, status, figure_title = data
                    full_file_path = os.path.join(self.directory_path, relative_path)
                else:
                    relative_path, status, original_path = data
                    full_file_path = os.path.join(self.directory_path, original_path)
                    logger.debug(f"Row {row}: relative_path={relative_path}, status={status}, original_path={original_path}")
            path_parts = relative_path.split(os.sep)
            display_path = os.path.join(path_parts[-2], path_parts[-1]) if len(path_parts) > 1 else path_parts[-1]
            self.table.insertRow(row)
            file_item = QTableWidgetItem(display_path)
            file_item.setTextAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            file_item.setToolTip(relative_path)
            self.table.setItem(row, 0, file_item)
            if self.current_mode == "tables":
                self.table.setItem(row, 1, QTableWidgetItem(table_caption))
                self.table.setItem(row, 2, QTableWidgetItem(width_issue))
            elif self.current_mode == "graphics":
                self.table.setItem(row, 1, QTableWidgetItem(status))
                self.table.setItem(row, 2, QTableWidgetItem(figure_title))
            elif self.current_mode == "filename":
                self.table.setItem(row, 1, QTableWidgetItem(status))
            self.file_paths.append(full_file_path)
            fix_btn = QPushButton("Fix")
            fix_btn.setFont(QFont("Helvetica", 9))
            fix_btn.setStyleSheet("""
                QPushButton {
                    background-color: #FF8C00;
                    color: #FFFFFF;
                    padding: 0px;
                    border-radius: 4px;
                    border: 1px solid #CC7000;
                    min-width: 60px;
                    min-height: 24px;
                    text-align: center;
                }
                QPushButton:hover {
                    background-color: #FFA500;
                    border: 1px solid #CC8400;
                }
                QPushButton:disabled {
                    background-color: #666666;
                    border: 1px solid #555555;
                }
            """)
            # Connect to handle_open_file for tables and graphics, handle_fix_filename for filename
            if self.current_mode in ("tables", "graphics"):
                fix_btn.clicked.connect(lambda _, r=row: self.handle_open_file(r))
            else:
                fix_btn.clicked.connect(lambda _, r=row: self.handle_fix_filename(r))
            self.table.setCellWidget(row, self.table.columnCount() - 1, fix_btn)
        header = self.table.horizontalHeader()
        if self.current_mode in ("graphics", "tables"):
            self.table.setColumnWidth(0, 200)
            self.table.setColumnWidth(1, 100)
            self.table.setColumnWidth(2, 100)
            self.table.setColumnWidth(3, 110)
            header.setSectionResizeMode(0, header.ResizeMode.Stretch)
            header.setSectionResizeMode(1, header.ResizeMode.Fixed)
            header.setSectionResizeMode(2, header.ResizeMode.Fixed)
            header.setSectionResizeMode(3, header.ResizeMode.Fixed)
        else:
            self.table.setColumnWidth(2, 110)
            header.setSectionResizeMode(0, header.ResizeMode.Stretch)
            header.setSectionResizeMode(1, header.ResizeMode.Stretch)
            header.setSectionResizeMode(2, header.ResizeMode.Fixed)
        self.table.updateGeometry()
        self._flush_handlers()
        logger.debug("Completed populate_table")

    def populate_table_toc(self):
        logger.debug("Entering populate_table_toc")
        self.feedback_label.setVisible(False)
        self.table.setVisible(True)
        self.table.setRowCount(0)
        self.file_paths = []
        self.selected_row = None
        chapter_data = validate_chapter_toc(self.ditamap_path)
        subchapter_data = validate_subchapter_toc(self.ditamap_path)
        if not chapter_data and not subchapter_data:
            self.feedback_label.setText("No chapter or subchapter TOC issues found")
            self.feedback_label.setVisible(True)
            self.table.setVisible(False)
            logger.info("No chapter or subchapter TOC issues found")
            self._flush_handlers()
            return
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Chapter Name", "Topic/SubTopic Title"])
        row = 0
        data_row = 0
        if chapter_data:
            # Add header for Chapter TOC
            self.table.insertRow(row)
            header_item = QTableWidgetItem("Missing Chapter TOC")
            header_item.setBackground(QBrush(QColor("#D3D3D3")))
            header_item.setFont(QFont("Helvetica", 10, QFont.Weight.Bold))
            self.table.setItem(row, 0, header_item)
            self.table.setSpan(row, 0, 1, 2)
            row += 1
            for chapter_name, topic_name, chapter_xml_path in chapter_data:
                self.table.insertRow(row)
                file_item = QTableWidgetItem(chapter_name)
                file_item.setTextAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
                self.table.setItem(row, 0, file_item)
                topic_item = QTableWidgetItem(topic_name)
                topic_item.setTextAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
                topic_item.setFlags(topic_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 1, topic_item)
                self.file_paths.append(chapter_xml_path)
                logger.debug(f"Chapter TOC row {row}, data_row {data_row}: Chapter={chapter_name}, Topic={topic_name}, Path={chapter_xml_path}")
                row += 1
                data_row += 1
        if subchapter_data:
            # Add header for SubChapter TOC
            self.table.insertRow(row)
            header_item = QTableWidgetItem("Missing SubChapter TOC")
            header_item.setBackground(QBrush(QColor("#D3D3D3")))
            header_item.setFont(QFont("Helvetica", 10, QFont.Weight.Bold))
            self.table.setItem(row, 0, header_item)
            self.table.setSpan(row, 0, 1, 2)
            row += 1
            for chapter_name, subtopic_name, chapter_xml_path in subchapter_data:
                self.table.insertRow(row)
                file_item = QTableWidgetItem(chapter_name)
                file_item.setTextAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
                self.table.setItem(row, 0, file_item)
                subtopic_item = QTableWidgetItem(subtopic_name)
                subtopic_item.setTextAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
                subtopic_item.setFlags(subtopic_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 1, subtopic_item)
                self.file_paths.append(chapter_xml_path)
                logger.debug(f"SubChapter TOC row {row}, data_row {data_row}: Chapter={chapter_name}, Subtopic={subtopic_name}, Path={chapter_xml_path}")
                row += 1
                data_row += 1
        self.table.setColumnWidth(1, 300)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        self.table.updateGeometry()
        self._flush_handlers()
        logger.debug(f"Completed populate_table_toc: Total rows: {row}, data_rows: {data_row}, file_paths length: {len(self.file_paths)}")

    def populate_table_empty_headings(self):
        logger.debug("Entering populate_table_empty_headings")
        self.feedback_label.setVisible(False)
        self.table.setVisible(True)
        self.table.setRowCount(0)
        self.file_paths = []
        self.href_map = {}
        self.selected_row = None
        table_data = validate_empty_headings(self.ditamap_path)
        logger.debug(f"Empty headings validation data: {table_data}")
        if not table_data:
            self.feedback_label.setText("No empty headings found")
            self.feedback_label.setVisible(True)
            self.table.setVisible(False)
            logger.info("No empty headings found")
            self._flush_handlers()
            return
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["File Name", "Folder Path", "Action"])
        for row, (file_name, folder_path, file_path, href) in enumerate(table_data):
            self.table.insertRow(row)
            file_item = QTableWidgetItem(file_name)
            file_item.setTextAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            self.table.setItem(row, 0, file_item)
            folder_item = QTableWidgetItem(folder_path)
            folder_item.setTextAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            folder_item.setToolTip(folder_path)
            self.table.setItem(row, 1, folder_item)
            self.file_paths.append(file_path)
            self.href_map[file_path] = href
            fix_btn = QPushButton("Fix")
            fix_btn.setFont(QFont("Helvetica", 9))
            fix_btn.setStyleSheet("""
                QPushButton {
                    background-color: #FF8C00;
                    color: #FFFFFF;
                    padding: 0px;
                    border-radius: 4px;
                    border: 1px solid #CC7000;
                    min-width: 60px;
                    min-height: 24px;
                    text-align: center;
                }
                QPushButton:hover {
                    background-color: #FFA500;
                    border: 1px solid #CC8400;
                }
                QPushButton:disabled {
                    background-color: #666666;
                    border: 1px solid #555555;
                }
            """)
            fix_btn.clicked.connect(lambda _, r=row: self.handle_fix_empty_heading(r))
            self.table.setCellWidget(row, 2, fix_btn)
            logger.debug(f"Added row {row}: file_name={file_name}, folder_path={folder_path}, file_path={file_path}, href={href}")
        header = self.table.horizontalHeader()
        self.table.setColumnWidth(0, 200)
        self.table.setColumnWidth(1, 300)
        self.table.setColumnWidth(2, 110)
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        header.setSectionResizeMode(2, header.ResizeMode.Fixed)
        self.table.updateGeometry()
        self._flush_handlers()
        logger.debug("Completed populate_table_empty_headings")

    def handle_refresh(self):
        logger.debug("Entering handle_refresh")
        if not self.directory_path and not self.ditamap_path:
            self.feedback_label.setText("No directory or DITA map selected. Please select first.")
            logger.debug("No directory or DITA map selected in handle_refresh")
            return
        if self.current_mode == "tables":
            self.table.setColumnCount(4)
            self.table.setHorizontalHeaderLabels(["File", "Table Caption", "Table Width", "Fix"])
            self.fix_all_btn.setVisible(False)
            self.populate_table(validate_tables)
        elif self.current_mode == "graphics":
            self.table.setColumnCount(4)
            self.table.setHorizontalHeaderLabels(["File", "Size Attributes", "Figure Title", "Fix"])
            self.fix_all_btn.setVisible(False)
            self.populate_table(validate_graphics)
        elif self.current_mode == "filename":
            self.table.setColumnCount(3)
            self.table.setHorizontalHeaderLabels(["File Name", "Topic Title", "Fix"])
            self.fix_all_btn.setVisible(True)
            self.populate_table(validate_filename)
        elif self.current_mode == "chapter_toc":
            self.table.setVisible(True)
            self.fix_all_btn.setVisible(False)
            self.populate_table_toc()
        elif self.current_mode == "empty_headings":
            self.table.setVisible(True)
            self.fix_all_btn.setVisible(True)
            self.populate_table_empty_headings()
        else:
            self.feedback_label.setText("Please select a check to refresh.")
            logger.debug("No valid mode selected in handle_refresh")
        self._flush_handlers()
        logger.debug("Completed handle_refresh")