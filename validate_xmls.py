import os
import logging
import uuid
import tempfile
from pathlib import Path
from urllib.parse import unquote, quote
from lxml import etree
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog, QTableWidget, QTableWidgetItem, QMenu, QApplication, QScrollArea, QFrame, QGridLayout, QSizePolicy
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QFont, QBrush, QColor, QDesktopServices, QPixmap
from markdown_viewer import MarkdownViewer
from remove_duplicate_ids import remove_duplicate_ids
from fix_tables import validate_tables
from fix_graphics import validate_graphics
from validate_chapter_toc import validate_chapter_toc, validate_subchapter_toc
from empty import update_xml_file, is_empty_except_title

# Set up logging with file output only (no console)
log_file = os.path.expanduser("~/Desktop/ftp_debug.log")
logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)  # Only errors will be logged
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Clear existing handlers to avoid duplicates
logging.getLogger('').handlers = []

# Add file handler with fallback
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

def validate_empty_headings(ditamap_path: str) -> list:
    """
    Validate XML files referenced in a DITA map for empty content except title.
    Returns files that have only a title and child topicrefs.
    """
    results = []
    base_dir = Path(ditamap_path).parent
    try:
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(str(ditamap_path), parser)
        namespaces = {'dita': 'http://dita.oasis-open.org/architecture/2005/'}
        
        topicrefs = tree.xpath("//dita:topicref | //topicref | //dita:chapter | //chapter", namespaces=namespaces)
        all_hrefs = [tr.get("href") for tr in topicrefs if tr.get("href")]
        
        for topicref in topicrefs:
            href = topicref.get("href")
            if not href:
                continue
            
            decoded_href = unquote(href).replace('\\', '/')
            try:
                xml_path = (base_dir / decoded_href).resolve()
                if not xml_path.exists():
                    continue
                if xml_path.suffix.lower() not in ('.xml', '.dita'):
                    continue
                
                child_hrefs = [child.get("href") for child in topicref.xpath("./dita:topicref | ./topicref", namespaces=namespaces) if child.get("href")]
                
                if is_empty_except_title(xml_path) and child_hrefs:
                    relative_path = xml_path.relative_to(base_dir)
                    folder_path = str(xml_path.parent)
                    file_name = xml_path.name
                    results.append((file_name, folder_path, str(xml_path), href))
            except (ValueError, OSError) as e:
                continue
    except etree.LxmlError as e:
        logger.error(f"Error parsing DITA map {ditamap_path}: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in validate_empty_headings for {ditamap_path}: {str(e)}")
    return results

class ValidateXMLsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.directory_path = ""
        self.ditamap_path = ""
        self.file_paths = []
        self.href_map = {}
        self.current_mode = ""
        self.selected_row = None
        self.button_info_labels = {}
        self.markdown_viewers = []

        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(5)
        self.setLayout(layout)

        button_panel = QHBoxLayout()
        button_panel.setSpacing(8)
        button_panel.setContentsMargins(0, 0, 0, 0)

        # Remove Duplicate IDs section
        remove_duplicate_ids_layout = QVBoxLayout()
        remove_duplicate_ids_icon_container = QWidget()
        remove_duplicate_ids_icon_container.setFixedHeight(40)
        remove_duplicate_ids_icon_layout = QHBoxLayout()
        remove_duplicate_ids_icon_container.setLayout(remove_duplicate_ids_icon_layout)
        remove_duplicate_ids_icon_container.setStyleSheet("background-color: transparent;")
        remove_duplicate_ids_info_label = QLabel()
        remove_duplicate_ids_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio)
            remove_duplicate_ids_info_label.setPixmap(pixmap)
            remove_duplicate_ids_info_label.update()
        else:
            pixmap = QPixmap(16, 16)
            pixmap.fill(Qt.GlobalColor.transparent)
            remove_duplicate_ids_info_label.setPixmap(pixmap)
        remove_duplicate_ids_info_label.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_duplicate_ids_info_label.setVisible(False)
        remove_duplicate_ids_info_label.mousePressEvent = lambda event: self.open_markdown_help("Remove Duplicate IDs")
        self.button_info_labels["Remove Duplicate IDs"] = remove_duplicate_ids_info_label
        remove_duplicate_ids_icon_layout.addWidget(remove_duplicate_ids_info_label)
        self.remove_duplicate_ids_btn = QPushButton("Remove Duplicate IDs")
        self.remove_duplicate_ids_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.remove_duplicate_ids_btn.setMinimumSize(150, 30)
        self.remove_duplicate_ids_btn.setStyleSheet("background-color: #0D6E6E; color: #FFFFFF; padding: 5px 10px; border-radius: 4px; border: 1px solid #0A5555;")
        remove_duplicate_ids_layout.addWidget(remove_duplicate_ids_icon_container)
        remove_duplicate_ids_layout.addWidget(self.remove_duplicate_ids_btn)
        button_panel.addLayout(remove_duplicate_ids_layout)

        # Validate Tables section
        validate_tables_layout = QVBoxLayout()
        validate_tables_icon_container = QWidget()
        validate_tables_icon_container.setFixedHeight(40)
        validate_tables_icon_layout = QHBoxLayout()
        validate_tables_icon_container.setLayout(validate_tables_icon_layout)
        validate_tables_icon_container.setStyleSheet("background-color: transparent;")
        validate_tables_info_label = QLabel()
        validate_tables_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio)
            validate_tables_info_label.setPixmap(pixmap)
            validate_tables_info_label.update()
        else:
            pixmap = QPixmap(16, 16)
            pixmap.fill(Qt.GlobalColor.transparent)
            validate_tables_info_label.setPixmap(pixmap)
        validate_tables_info_label.setCursor(Qt.CursorShape.PointingHandCursor)
        validate_tables_info_label.setVisible(False)
        validate_tables_info_label.mousePressEvent = lambda event: self.open_markdown_help("Validate Tables")
        self.button_info_labels["Validate Tables"] = validate_tables_info_label
        validate_tables_icon_layout.addWidget(validate_tables_info_label)
        self.validate_tables_btn = QPushButton("Validate Tables")
        self.validate_tables_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.validate_tables_btn.setMinimumSize(150, 30)
        self.validate_tables_btn.setStyleSheet("background-color: #0D6E6E; color: #FFFFFF; padding: 5px 10px; border-radius: 4px; border: 1px solid #0A5555;")
        validate_tables_layout.addWidget(validate_tables_icon_container)
        validate_tables_layout.addWidget(self.validate_tables_btn)
        button_panel.addLayout(validate_tables_layout)

        # Validate Graphics section
        validate_graphics_layout = QVBoxLayout()
        validate_graphics_icon_container = QWidget()
        validate_graphics_icon_container.setFixedHeight(40)
        validate_graphics_icon_layout = QHBoxLayout()
        validate_graphics_icon_container.setLayout(validate_graphics_icon_layout)
        validate_graphics_icon_container.setStyleSheet("background-color: transparent;")
        validate_graphics_info_label = QLabel()
        validate_graphics_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio)
            validate_graphics_info_label.setPixmap(pixmap)
            validate_graphics_info_label.update()
        else:
            pixmap = QPixmap(16, 16)
            pixmap.fill(Qt.GlobalColor.transparent)
            validate_graphics_info_label.setPixmap(pixmap)
        validate_graphics_info_label.setCursor(Qt.CursorShape.PointingHandCursor)
        validate_graphics_info_label.setVisible(False)
        validate_graphics_info_label.mousePressEvent = lambda event: self.open_markdown_help("Validate Graphics")
        self.button_info_labels["Validate Graphics"] = validate_graphics_info_label
        validate_graphics_icon_layout.addWidget(validate_graphics_info_label)
        self.validate_graphics_btn = QPushButton("Validate Graphics")
        self.validate_graphics_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.validate_tables_btn.setMinimumSize(150, 30)
        self.validate_graphics_btn.setStyleSheet("background-color: #0D6E6E; color: #FFFFFF; padding: 5px 10px; border-radius: 4px; border: 1px solid #0A5555;")
        validate_graphics_layout.addWidget(validate_graphics_icon_container)
        validate_graphics_layout.addWidget(self.validate_graphics_btn)
        button_panel.addLayout(validate_graphics_layout)

        # Validate Chapter TOC section
        validate_chapter_toc_layout = QVBoxLayout()
        validate_chapter_toc_icon_container = QWidget()
        validate_chapter_toc_icon_container.setFixedHeight(40)
        validate_chapter_toc_icon_layout = QHBoxLayout()
        validate_chapter_toc_icon_container.setLayout(validate_chapter_toc_icon_layout)
        validate_chapter_toc_icon_container.setStyleSheet("background-color: #1F252A;")
        validate_chapter_toc_info_label = QLabel()
        validate_chapter_toc_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio)
            validate_chapter_toc_info_label.setPixmap(pixmap)
            validate_chapter_toc_info_label.update()
        else:
            pixmap = QPixmap(16, 16)
            pixmap.fill(Qt.GlobalColor.transparent)
            validate_chapter_toc_info_label.setPixmap(pixmap)
        validate_chapter_toc_info_label.setCursor(Qt.CursorShape.PointingHandCursor)
        validate_chapter_toc_info_label.setVisible(False)
        validate_chapter_toc_info_label.mousePressEvent = lambda event: self.open_markdown_help("Validate Chapter TOC")
        self.button_info_labels["Validate Chapter TOC"] = validate_chapter_toc_info_label
        validate_chapter_toc_icon_layout.addWidget(validate_chapter_toc_info_label)
        self.validate_chapter_toc_btn = QPushButton("Validate Chapter TOC")
        self.validate_chapter_toc_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.validate_chapter_toc_btn.setMinimumSize(150, 30)
        self.validate_chapter_toc_btn.setStyleSheet("background-color: #0D6E6E; color: #FFFFFF; padding: 5px 10px; border-radius: 4px; border: 1px solid #0A5555;")
        validate_chapter_toc_layout.addWidget(validate_chapter_toc_icon_container)
        validate_chapter_toc_layout.addWidget(self.validate_chapter_toc_btn)
        button_panel.addLayout(validate_chapter_toc_layout)

        # Fix Empty Headings section
        fix_empty_headings_layout = QVBoxLayout()
        fix_empty_headings_icon_container = QWidget()
        fix_empty_headings_icon_container.setFixedHeight(40)
        fix_empty_headings_icon_layout = QHBoxLayout()
        fix_empty_headings_icon_container.setLayout(fix_empty_headings_icon_layout)
        fix_empty_headings_icon_container.setStyleSheet("background-color: transparent;")
        fix_empty_headings_info_label = QLabel()
        fix_empty_headings_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio)
            fix_empty_headings_info_label.setPixmap(pixmap)
            fix_empty_headings_info_label.update()
        else:
            pixmap = QPixmap(16, 16)
            pixmap.fill(Qt.GlobalColor.transparent)
            fix_empty_headings_info_label.setPixmap(pixmap)
        fix_empty_headings_info_label.setCursor(Qt.CursorShape.PointingHandCursor)
        fix_empty_headings_info_label.setVisible(False)
        fix_empty_headings_info_label.mousePressEvent = lambda event: self.open_markdown_help("Fix Empty Headings")
        self.button_info_labels["Fix Empty Headings"] = fix_empty_headings_info_label
        fix_empty_headings_icon_layout.addWidget(fix_empty_headings_info_label)
        self.fix_empty_headings_btn = QPushButton("Fix Empty Headings")
        self.fix_empty_headings_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.fix_empty_headings_btn.setMinimumSize(150, 30)
        self.fix_empty_headings_btn.setStyleSheet("background-color: #0D6E6E; color: #FFFFFF; padding: 5px 10px; border-radius: 4px; border: 1px solid #0A5555;")
        fix_empty_headings_layout.addWidget(fix_empty_headings_icon_container)
        fix_empty_headings_layout.addWidget(self.fix_empty_headings_btn)
        button_panel.addLayout(fix_empty_headings_layout)

        layout.addLayout(button_panel)

        self.feedback_label = QLabel("Select a check to begin")
        self.feedback_label.setFont(QFont("Helvetica", 14, QFont.Weight.Bold))
        self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
        self.feedback_label.setVisible(True)
        self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.feedback_label)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.container = QWidget()
        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        self.container.setLayout(self.main_layout)
        self.scroll_area.setWidget(self.container)
        self.scroll_area.setVisible(False)
        layout.addWidget(self.scroll_area)

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
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #E6ECEF;
                color: #121416;
                border-radius: 4px;
                padding: 3px;
            }
            QTableWidget::item {
                background-color: #E6ECEF;
                color: #0000FF;
                font-weight: bold;
                padding: 2px;
                margin: 0px;
                text-decoration: underline;
            }
            QTableWidget QHeaderView::section {
                background-color: #E6ECEF;
                color: #000000;
                font-weight: bold;
            }
            QTableWidget QLabel {
                background: none;
            }
            /* Custom styling for empty_headings mode */
            QTableWidget#empty_headings_table::item {
                background-color: #000000;
                color: #FFFFFF;
            }
        """)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(30)
        layout.addWidget(self.table)

        bottom_panel = QHBoxLayout()
        bottom_panel.setSpacing(8)

        # Refresh section
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.refresh_btn.setMinimumSize(150, 30)
        self.refresh_btn.setStyleSheet("background-color: #0D6E6E; color: #FFFFFF; padding: 5px 10px; border-radius: 4px; border: 1px solid #0A5555;")
        bottom_panel.addWidget(self.refresh_btn)

        # Fix All section
        self.fix_all_btn = QPushButton("Fix All")
        self.fix_all_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.fix_all_btn.setMinimumSize(150, 30)
        self.fix_all_btn.setStyleSheet("background-color: #0D6E6E; color: #FFFFFF; padding: 5px 10px; border-radius: 4px; border: 1px solid #0A5555;")
        self.fix_all_btn.setVisible(False)
        self.fix_all_btn.clicked.connect(self.handle_fix_all)
        bottom_panel.addWidget(self.fix_all_btn)

        # Back to Menu section
        self.back_btn = QPushButton("Back to Menu")
        self.back_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.back_btn.setMinimumSize(150, 30)
        self.back_btn.setStyleSheet("background-color: #0D6E6E; color: #FFFFFF; padding: 5px 10px; border-radius: 4px; border: 1px solid #0A5555;")
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
                min-width: 150px;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #139999;
                border: 1px solid #0C7A7A;
            }
            QPushButton:disabled {
                background-color: #666666;
                border: 1px solid #555555;
            }
            QScrollArea {
                background-color: #1F252A;
                border: none;
            }
            QFrame {
                background-color: transparent;
                border: none;
                height: 0px;
                min-height: 0px;
                min-width: 0px;
            }
            QLabel {
                background: #FFFFFF;
            }
        """)

        self.remove_duplicate_ids_btn.clicked.connect(self.handle_remove_duplicate_ids)
        self.validate_tables_btn.clicked.connect(self.handle_validate_tables)
        self.validate_graphics_btn.clicked.connect(self.handle_validate_graphics)
        self.validate_chapter_toc_btn.clicked.connect(self.handle_validate_chapter_toc)
        self.fix_empty_headings_btn.clicked.connect(self.handle_fix_empty_headings)
        self.refresh_btn.clicked.connect(self.handle_refresh)
        self.back_btn.clicked.connect(self.parent_window.return_to_main_menu)

    def open_markdown_help(self, button_name):
        """Open the corresponding .md file for the button."""
        md_name = button_name.lower().replace(" ", "_") + ".md"
        md_path = os.path.join(os.path.dirname(__file__), "docs", md_name)
        if not os.path.exists(md_path):
            logger.warning(f"Markdown file not found at {md_path}")
            return
        viewer = MarkdownViewer(md_path, button_name, self.parent_window)
        viewer.show()
        self.markdown_viewers.append(viewer)

    def update_help_ui(self):
        """Show/hide info icons based on parent window's help_enabled state."""
        help_enabled = self.parent_window.help_enabled if self.parent_window else False
        for label_name, label in self.button_info_labels.items():
            label.setVisible(help_enabled)
            if help_enabled and not label.pixmap().isNull():
                pass

    def show_context_menu(self, pos):
        index = self.table.indexAt(pos)
        if not index.isValid() or index.column() != 0 or self.current_mode != "chapter_toc":
            return

        menu = QMenu(self)
        copy_action = menu.addAction("Copy File Name")
        action = menu.exec(self.table.mapToGlobal(pos))
        if action == copy_action:
            row = index.row()
            file_path = self.file_paths[row]
            QApplication.clipboard().setText(file_path)
            pass

            item = self.table.item(row, 0)
            if item:
                item.setBackground(QBrush(QColor("#FFA500")))
                QTimer.singleShot(1000, lambda: item.setBackground(QBrush(QColor("#E6ECEF"))))

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
            duplicates_fixed, files_modified, log_success = remove_duplicate_ids(self, self.directory_path)
            message = f"Fixed {duplicates_fixed} duplicates in {files_modified} files"
            if not log_success:
                message += ". Warning: Failed to create LegacyTextTuring/legacy_duplicate_log.txt in parent directory"
            self.feedback_label.setText(message)
        except Exception as e:
            self.feedback_label.setText(f"Error: {str(e)}")
        self._flush_handlers()

    def handle_validate_tables(self):
        self.directory_path = QFileDialog.getExistingDirectory(self, "Select Directory", "")
        if not self.directory_path:
            self.feedback_label.setText("No directory selected")
            return
        self.current_mode = "tables"
        self.table.setVisible(True)
        self.scroll_area.setVisible(False)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["File", "Table Title", "Table Width", "Open"])
        self.fix_all_btn.setVisible(False)
        self.populate_table(validate_tables)

    def handle_validate_graphics(self):
        self.directory_path = QFileDialog.getExistingDirectory(self, "Select Directory", "")
        if not self.directory_path:
            self.feedback_label.setText("No directory selected")
            return
        self.current_mode = "graphics"
        self.table.setVisible(True)
        self.scroll_area.setVisible(False)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["File", "Size Attributes", "Figure Title", "Open"])
        self.fix_all_btn.setVisible(False)
        self.populate_table(validate_graphics)

    def handle_validate_chapter_toc(self):
        self.ditamap_path = QFileDialog.getOpenFileName(
            self, "Select DITA Map", "", "DITA Map Files (*.ditamap);;All Files (*)"
        )[0]
        if not self.ditamap_path:
            self.feedback_label.setText("No DITA map selected")
            return
        self.directory_path = str(Path(self.ditamap_path).parent)
        self.current_mode = "chapter_toc"
        self.table.setVisible(False)
        self.scroll_area.setVisible(True)
        self.fix_all_btn.setVisible(False)
        self.populate_text_list_toc()

    def handle_fix_empty_headings(self):
        self.ditamap_path = QFileDialog.getOpenFileName(
            self, "Select DITA Map", "", "DITA Map Files (*.ditamap);;All Files (*)"
        )[0]
        if not self.ditamap_path:
            self.feedback_label.setText("No DITA map selected")
            return
        self.directory_path = str(Path(self.ditamap_path).parent)
        self.current_mode = "empty_headings"
        self.table.setObjectName("empty_headings_table")
        self.table.setVisible(True)
        self.scroll_area.setVisible(False)
        self.fix_all_btn.setVisible(True)
        parent_dir = os.path.dirname(self.ditamap_path)
        log_file = os.path.join(parent_dir, "LegacyTextTuring", "Log.txt")
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        if not os.path.exists(log_file) or os.path.getsize(log_file) == 0:
            with open(log_file, 'a') as f:
                f.write("---------------------------------------------------------\nFixed Empty XMLs:\n")
        self.populate_table_empty_headings()

    def handle_fix_empty_heading(self, row):
        if self.current_mode != "empty_headings":
            self.feedback_label.setText("Fix only available in Fix Empty Headings mode")
            return
        try:
            file_path = self.file_paths[row]
            href = self.href_map.get(file_path)
            if not href:
                self.feedback_label.setText(f"No href found for {os.path.basename(file_path)}")
                return
            
            parser = etree.XMLParser(recover=True)
            tree = etree.parse(self.ditamap_path, parser)
            namespaces = {'dita': 'http://dita.oasis-open.org/architecture/2005/'}
            
            decoded_href = unquote(href).replace('\\', '/')
            
            topicref = tree.xpath(
                f"//dita:topicref[@href='{href}' or @href='{decoded_href}'] | "
                f"//topicref[@href='{href}' or @href='{decoded_href}'] | "
                f"//dita:chapter[@href='{href}' or @href='{decoded_href}'] | "
                f"//chapter[@href='{href}' or @href='{decoded_href}']",
                namespaces=namespaces
            )
            
            if not topicref:
                self.feedback_label.setText(f"No topicref found for {os.path.basename(file_path)}")
                return
            
            child_hrefs = [child.get("href") for child in topicref[0].xpath("./dita:topicref | ./topicref", namespaces=namespaces) if child.get("href")]
            
            if not child_hrefs:
                self.feedback_label.setText(f"No child topics found for {os.path.basename(file_path)}")
                return
            
            if update_xml_file(file_path, child_hrefs, self.ditamap_path):
                if not os.path.exists(file_path):
                    raise FileNotFoundError(f"The file {file_path} does not exist.")
                url = QUrl.fromLocalFile(file_path)
                QDesktopServices.openUrl(url)
                self.feedback_label.setText(f"Fixed and opened {os.path.basename(file_path)}")
                self.table.removeRow(row)
                self.file_paths.pop(row)
                del self.href_map[file_path]
            else:
                self.feedback_label.setText(f"Failed to fix {os.path.basename(file_path)}")
        except Exception as e:
            self.feedback_label.setText(f"Error fixing file: {str(e)}")
        self._flush_handlers()

    def handle_fix_all(self):
        if self.current_mode == "empty_headings":
            self.handle_fix_all_empty_headings()
        else:
            self.feedback_label.setText("Fix All only available in Fix Empty Headings mode")

    def handle_fix_all_empty_headings(self):
        if self.current_mode != "empty_headings":
            self.feedback_label.setText("Fix All only available in Fix Empty Headings mode")
            return
        total_files = self.table.rowCount()
        if total_files == 0:
            self.feedback_label.setText("No files to fix")
            return
        success_count = 0
        failed_count = 0
        parent_dir = os.path.dirname(self.ditamap_path)
        log_file = os.path.join(parent_dir, "LegacyTextTuring", "Log.txt")
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        if not os.path.exists(log_file) or os.path.getsize(log_file) == 0:
            with open(log_file, 'a') as f:
                f.write("---------------------------------------------------------\nFixed Empty XMLs:\n")
        try:
            parser = etree.XMLParser(recover=True)
            tree = etree.parse(self.ditamap_path, parser)
            namespaces = {'dita': 'http://dita.oasis-open.org/architecture/2005/'}
            
            for row in range(total_files - 1, -1, -1):
                file_path = self.file_paths[row]
                href = self.href_map.get(file_path)
                if not href:
                    failed_count += 1
                    self.feedback_label.setText(f"Skipped {os.path.basename(file_path)}: No href found")
                    continue
                
                try:
                    decoded_href = unquote(href).replace('\\', '/')
                    
                    topicref = tree.xpath(
                        f"//dita:topicref[@href='{href}' or @href='{decoded_href}'] | "
                        f"//topicref[@href='{href}' or @href='{decoded_href}'] | "
                        f"//dita:chapter[@href='{href}' or @href='{decoded_href}'] | "
                        f"//chapter[@href='{href}' or @href='{decoded_href}']",
                        namespaces=namespaces
                    )
                    
                    if not topicref:
                        failed_count += 1
                        self.feedback_label.setText(f"Skipped {os.path.basename(file_path)}: No topicref found")
                        continue
                    
                    child_hrefs = [child.get("href") for child in topicref[0].xpath("./dita:topicref | ./topicref", namespaces=namespaces) if child.get("href")]
                    
                    if not child_hrefs:
                        failed_count += 1
                        self.feedback_label.setText(f"Skipped {os.path.basename(file_path)}: No child topics")
                        continue
                    
                    if update_xml_file(file_path, child_hrefs, self.ditamap_path):
                        success_count += 1
                        self.table.removeRow(row)
                        self.file_paths.pop(row)
                        del self.href_map[file_path]
                        self.feedback_label.setText(f"Fixed {os.path.basename(file_path)}")
                    else:
                        failed_count += 1
                        self.feedback_label.setText(f"Failed to fix {os.path.basename(file_path)}")
                except Exception as e:
                    failed_count += 1
                    self.feedback_label.setText(f"Error fixing {os.path.basename(file_path)}: {str(e)}")
        except Exception as e:
            self.feedback_label.setText(f"Error during Fix All: {str(e)}")
            return
        
        message = f"Added mini-TOC in {success_count} Topics"
        if failed_count > 0:
            message += f", {failed_count} failures"
        self.feedback_label.setText(message)
        
        if self.table.rowCount() == 0:
            self.table.setColumnCount(3)
            self.table.setHorizontalHeaderLabels(["File Name", "Folder Path", "Action"])
            self.populate_table_empty_headings()
            if self.table.rowCount() == 0:
                self.feedback_label.setText(f"{message}. No Empty XMLs Found in the Directory")
                self.table.setVisible(False)
                self.fix_all_btn.setVisible(False)
        self._flush_handlers()

    def handle_open_file(self, file_path):
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"The file {file_path} does not exist.")
            url = QUrl.fromLocalFile(file_path)
            QDesktopServices.openUrl(url)
            self.feedback_label.setText(f"Opened {os.path.basename(file_path)}")
        except Exception as e:
            self.feedback_label.setText(f"Error opening file: {str(e)}")
        self._flush_handlers()

    def handle_cell_click(self, row=None, column=None, file_path=None):
        if file_path:
            self.handle_open_file(file_path)
            return
        if row is None or column is None or row < 0 or row >= len(self.file_paths):
            return
        if self.current_mode == "chapter_toc" and column == 1:
            item = self.table.item(row, 0)
            if item and item.text() in ("Missing Chapter TOC", "Missing Subchapter TOC"):
                return
            data_row = row
            for i in range(row):
                if self.table.item(i, 0) and self.table.item(i, 0).text() in ["Missing Chapter TOC", "Missing Subchapter TOC"]:
                    data_row -= 1
            if data_row < 0 or data_row >= len(self.file_paths):
                return
            file_path = self.file_paths[data_row]
            self.handle_open_file(file_path)
        elif self.current_mode == "empty_headings" and column in (0, 1):
            file_path = self.file_paths[row]
            if column == 0:
                self.handle_open_file(file_path)
            elif column == 1:
                folder_path = self.table.item(row, 1).toolTip()
                try:
                    if not os.path.exists(folder_path):
                        raise FileNotFoundError(f"The folder {folder_path} does not exist.")
                    url = QUrl.fromLocalFile(folder_path)
                    QDesktopServices.openUrl(url)
                except Exception as e:
                    self.feedback_label.setText(f"Error opening folder: {str(e)}")
        self._flush_handlers()

    def build_ditamap_hrefs(self):
        hrefs = []
        missing_hrefs = []
        title_map = {}
        if not self.ditamap_path:
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
                abs_href = os.path.normpath(os.path.join(ditamap_dir, decoded_href.split('#')[0])).replace('\\', '/')
                rel_href = os.path.relpath(abs_href, ditamap_dir).replace('\\', '/')
                if os.path.exists(abs_href):
                    try:
                        file_tree = etree.parse(abs_href)
                        title_elem = file_tree.xpath("//title")
                        title = title_elem[0].text.strip() if title_elem and title_elem[0].text else os.path.splitext(os.path.basename(abs_href))[0]
                        if title in title_map:
                            pass
                        else:
                            title_map[title] = abs_href
                    except Exception as e:
                        pass
                    hrefs.append((href, rel_href, abs_href))
                else:
                    missing_hrefs.append(href)
        except Exception as e:
            pass
        return hrefs, missing_hrefs

    def update_sectional_bookmarks(self, file_path, rename_tracker, rename_map, ditamap_dir, is_ditamap=False):
        try:
            tree = etree.parse(file_path)
            modified = False
            elements = tree.xpath("//*[self::xref][@href]")
            file_dir = os.path.dirname(file_path)
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
                            element.set("href", quote(new_href, safe='/') + fragment)
                            matched = True
                            modified = True
                
                if not matched:
                    for original_abs_path, new_filename in rename_map.items():
                        original_abs_path_norm = original_abs_path.replace('\\', '/')
                        if abs_href == original_abs_path_norm and new_filename != os.path.basename(original_abs_path_norm):
                            new_href = os.path.join(os.path.dirname(decoded_href), new_filename)
                            element.set("href", quote(new_href, safe='/') + fragment)
                            matched = True
                            modified = True
                
                if not matched:
                    pass
            
            if modified:
                tree.write(file_path, encoding=tree.docinfo.encoding,
                         doctype=tree.docinfo.doctype, pretty_print=False,
                         xml_declaration=True)
            return modified
        except Exception as e:
            return False

    def update_ditamap_topicrefs(self, file_path, rename_tracker, rename_map):
        try:
            tree = etree.parse(file_path)
            modified = False
            elements = tree.xpath("//*[self::topicref][@href]")
            ditamap_dir = os.path.dirname(file_path)
            for element in elements:
                href = element.get("href")
                if not href or href.startswith(('http://', 'https://', 'mailto:')):
                    continue
                decoded_href = unquote(href).replace('\\', '/')
                abs_href = os.path.normpath(os.path.join(ditamap_dir, decoded_href.split('#')[0])).replace('\\', '/')
                path_parts = decoded_href.rsplit('/', 1)
                if len(path_parts) < 2:
                    continue
                dir_path, filename = path_parts
                matched = False
                
                for chapter, mappings in rename_tracker.items():
                    for original_abs_path, new_filename in mappings.items():
                        original_abs_path_norm = original_abs_path.replace('\\', '/')
                        if abs_href == original_abs_path_norm and new_filename != os.path.basename(original_abs_path_norm):
                            new_href = f"{dir_path}/{new_filename}"
                            element.set("href", new_href)
                            matched = True
                            modified = True
                
                if not matched:
                    for original_abs_path, new_filename in rename_map.items():
                        original_abs_path_norm = original_abs_path.replace('\\', '/')
                        if abs_href == original_abs_path_norm and new_filename != os.path.basename(original_abs_path_norm):
                            new_href = f"{dir_path}/{new_filename}"
                            element.set("href", new_href)
                            matched = True
                            modified = True
                
                if not matched:
                    pass
            
            if modified:
                tree.write(file_path, encoding=tree.docinfo.encoding,
                         doctype=tree.docinfo.doctype, pretty_print=False,
                         xml_declaration=True)
            return modified
        except Exception as e:
            return False

    def update_xref_references(self, rename_tracker: dict, rename_map: dict):
        success_count = 0
        error_messages = []
        modified_files = []
        unmatched_hrefs = []
        case_warnings = []
        ditamap_dir = os.path.dirname(self.ditamap_path) if self.ditamap_path else os.path.dirname(self.directory_path)

        def update_file(file_path, is_ditamap=False):
            nonlocal success_count, modified_files, unmatched_hrefs, case_warnings
            try:
                tree = etree.parse(file_path)
                modified = False
                elements = tree.xpath("//*[self::chapter or self::topicref or self::xref or self::appendix][@href]")
                file_dir = os.path.dirname(file_path)
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
                        pass
                    rel_href = os.path.relpath(abs_href, ditamap_dir).replace('\\', '/')
                    new_href = decoded_href
                    matched = False
                    
                    for chapter, mappings in rename_tracker.items():
                        for original_abs_path, new_filename in mappings.items():
                            original_abs_path_norm = original_abs_path.replace('\\', '/')
                            if abs_href == original_abs_path_norm and new_filename != os.path.basename(original_abs_path_norm):
                                new_href = os.path.join(os.path.dirname(decoded_href), new_filename)
                                element.set("href", quote(new_href, safe='/'))
                                matched = True
                                modified = True
                    
                    if not matched:
                        for original_abs_path, new_filename in rename_map.items():
                            original_abs_path_norm = original_abs_path.replace('\\', '/')
                            if abs_href == original_abs_path_norm and new_filename != os.path.basename(original_abs_path_norm):
                                new_href = os.path.join(os.path.dirname(decoded_href), new_filename)
                                element.set("href", quote(new_href, safe='/'))
                                matched = True
                                modified = True
                            elif rel_href == os.path.relpath(original_abs_path_norm, ditamap_dir).replace('\\', '/'):
                                new_href = os.path.join(os.path.dirname(rel_href), new_filename)
                                element.set("href", quote(new_href, safe='/'))
                                matched = True
                                modified = True
                            if not matched and len(unmatched_hrefs) < 100:
                                unmatched_hrefs.append(f"Unmatched href in {file_path}: {href}")
                    
                    if os.path.exists(abs_href) and os.path.basename(abs_href) != os.path.basename(unquote(new_href)):
                        case_warnings.append(f"Case mismatch in {file_path}: {os.path.basename(abs_href)} vs {os.path.basename(unquote(new_href))}")
                
                if modified:
                    modified_files.append(file_path)
                    tree.write(file_path, encoding=tree.docinfo.encoding,
                             doctype=tree.docinfo.doctype, pretty_print=False,
                             xml_declaration=True)
                    success_count += 1
            except Exception as e:
                error_messages.append(f"Failed to parse file: {os.path.basename(file_path)}: {str(e)}")
            except OSError as e:
                error_messages.append(f"Failed to update file {os.path.basename(file_path)}: {str(e)}")

        for root, _, files in os.walk(self.directory_path):
            for file in files:
                if file.endswith(".xml") and "LegacyTextTuring" not in root:
                    file_path = os.path.join(root, file)
                    update_file(file_path, is_ditamap=False)
                    self.update_sectional_bookmarks(file_path, {}, {}, ditamap_dir, is_ditamap=False)
        try:
            parent_dir = os.path.dirname(self.directory_path)
            if not os.path.exists(parent_dir):
                error_messages.append(f"Parent directory not found: {parent_dir}")
            else:
                ditamap_files = [f for f in os.listdir(parent_dir) if f.endswith(".ditamap")]
                if not ditamap_files:
                    error_messages.append("No .ditamap files found in parent directory")
                for file in ditamap_files:
                    file_path = os.path.join(parent_dir, file)
                    if os.path.isfile(file_path):
                        update_file(file_path, is_ditamap=True)
                        self.update_sectional_bookmarks(file_path, {}, {}, ditamap_dir, is_ditamap=True)
                        self.update_ditamap_topicrefs(file_path, {}, {})
        except Exception as e:
            error_messages.append(f"Error accessing parent directory: {str(e)}")
        return success_count, error_messages, len(ditamap_files)

    def populate_table(self, validation_func):
        self.feedback_label.setVisible(False)
        self.table.setVisible(True)
        self.scroll_area.setVisible(False)
        self.table.setRowCount(0)
        self.file_paths = []
        self.selected_row = None
        table_data = validation_func(self.directory_path)
        if not table_data:
            self.feedback_label.setText("No issues found")
            self.feedback_label.setVisible(True)
            self.table.setVisible(False)
            self.scroll_area.setVisible(False)
            return
        if self.current_mode == "tables" or self.current_mode == "graphics":
            self.table.setColumnCount(4)
            if self.current_mode == "tables":
                self.table.setHorizontalHeaderLabels(["File", "Table Title", "Table Width", "Open"])
            else:
                self.table.setHorizontalHeaderLabels(["File", "Size Attributes", "Figure Title", "Open"])
        for row, data in enumerate(table_data):
            if self.current_mode == "tables":
                relative_path, table_title, width_issue = data
                full_file_path = os.path.join(self.directory_path, relative_path)
            elif self.current_mode == "graphics":
                relative_path, status, figure_title = data
                full_file_path = os.path.join(self.directory_path, relative_path)
            path_parts = relative_path.split(os.sep)
            display_path = os.path.join(path_parts[-2], path_parts[-1]) if len(path_parts) > 1 else path_parts[-1]
            self.table.insertRow(row)
            file_item = QTableWidgetItem(display_path)
            file_item.setTextAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            file_item.setToolTip(relative_path)
            file_item.setBackground(QBrush(QColor("#E6ECEF")))
            self.table.setItem(row, 0, file_item)
            if self.current_mode == "tables":
                caption_item = QTableWidgetItem(table_title)
                caption_item.setBackground(QBrush(QColor("#E6ECEF")))
                self.table.setItem(row, 1, caption_item)
                width_item = QTableWidgetItem(width_issue)
                width_item.setBackground(QBrush(QColor("#E6ECEF")))
                self.table.setItem(row, 2, width_item)
            elif self.current_mode == "graphics":
                status_item = QTableWidgetItem(status)
                status_item.setBackground(QBrush(QColor("#E6ECEF")))
                self.table.setItem(row, 1, status_item)
                title_item = QTableWidgetItem(figure_title)
                title_item.setBackground(QBrush(QColor("#E6ECEF")))
                self.table.setItem(row, 2, title_item)
            self.file_paths.append(full_file_path)
            open_btn = QPushButton("Open")
            open_btn.setFont(QFont("Helvetica", 9))
            open_btn.setStyleSheet("background-color: #0D6E6E; color: #FFFFFF; padding: 0px; border-radius: 4px; border: 1px solid #0A5555; min-width: 60px; min-height: 24px; text-align: center;")
            open_btn.clicked.connect(lambda _, r=full_file_path: self.handle_open_file(r))
            open_btn.setMinimumSize(60, 24)
            self.table.setCellWidget(row, self.table.columnCount() - 1, open_btn)
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
        self.table.updateGeometry()
        self._flush_handlers()

    def populate_text_list_toc(self):
        self.feedback_label.setVisible(False)
        self.table.setVisible(False)
        self.scroll_area.setVisible(True)
        self.fix_all_btn.setVisible(False)

        # Clear existing content
        for i in reversed(range(self.main_layout.count())):
            widget = self.main_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        # Add header
        header_label = QLabel("Missing Topics and Subtopics from Mini-TOC")
        header_label.setFont(QFont("Helvetica", 14, QFont.Weight.Bold))
        header_label.setStyleSheet("color: #121416; background: #FFFFFF;")
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(header_label)

        chapter_data = validate_chapter_toc(self.ditamap_path)
        subchapter_data = validate_subchapter_toc(self.ditamap_path)
        
        if not chapter_data and not subchapter_data:
            self.feedback_label.setText("No chapter or subchapter TOC issues found")
            self.feedback_label.setVisible(True)
            self.scroll_area.setVisible(False)
            return

        # Group data by chapter
        chapter_issues = {}
        for chapter_name, topic_name, chapter_xml_path in chapter_data:
            if chapter_name not in chapter_issues:
                chapter_issues[chapter_name] = {'topics': [], 'subtopics': [], 'file_path': chapter_xml_path}
            chapter_issues[chapter_name]['topics'].append((topic_name, chapter_xml_path))

        for chapter_name, subtopic_name, parent_xml_path, subtopic_file_path in subchapter_data:
            if chapter_name not in chapter_issues:
                chapter_issues[chapter_name] = {'topics': [], 'subtopics': [], 'file_path': parent_xml_path}
            chapter_issues[chapter_name]['subtopics'].append((subtopic_name, subtopic_file_path))

        self.file_paths = []

        # Helper function to extract missing file name from topic/subtopic name
        def extract_missing_file(name):
            try:
                cleaned_name = name.replace('\n', ' ').split(': ', 1)[1].split(' (', 1)[0]
                return cleaned_name
            except IndexError:
                return "Unknown"

        max_width = 0
        # Populate UI with corrected file names and ensure clickability
        for chapter_name, issues in chapter_issues.items():
            chapter_label = QLabel(f"{chapter_name}.xml")
            chapter_label.setFont(QFont("Helvetica", 11, QFont.Weight.Bold))
            chapter_label.setStyleSheet("color: #121416; background: #FFFFFF;")
            self.file_paths.append(issues['file_path'])
            chapter_label.setMouseTracking(True)
            chapter_label.mousePressEvent = lambda event, fp=issues['file_path']: self.handle_cell_click(file_path=fp)
            self.main_layout.addWidget(chapter_label)

            for topic_name, topic_file_path in issues['topics']:
                missing_topic_file = extract_missing_file(topic_name)
                topic_label = QLabel(f"  Missing Topic: {missing_topic_file}")
                topic_label.setFont(QFont("Helvetica", 10))
                topic_label.setStyleSheet("color: #0000FF; text-decoration: underline; background: #FFFFFF;")
                font_metrics = topic_label.fontMetrics()
                min_width = font_metrics.boundingRect(missing_topic_file).width() + 100
                topic_label.setMinimumWidth(min_width)
                max_width = max(max_width, min_width)
                topic_label.setWordWrap(False)
                topic_label.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred))
                self.file_paths.append(topic_file_path)
                topic_label.setMouseTracking(True)
                topic_label.setCursor(Qt.CursorShape.PointingHandCursor)
                topic_label.mousePressEvent = lambda event, fp=topic_file_path: self.handle_cell_click(file_path=fp)
                self.main_layout.addWidget(topic_label)

            for subtopic_name, subtopic_file_path in issues['subtopics']:
                missing_subtopic_file = extract_missing_file(subtopic_name)
                subtopic_label = QLabel(f"    Missing Subtopic: {missing_subtopic_file}")
                subtopic_label.setFont(QFont("Helvetica", 10))
                style = "color: #0000FF; text-decoration: underline; background: #FFFFFF;"
                if not os.path.exists(subtopic_file_path):
                    style = "color: #FF0000; text-decoration: underline; background: #FFFFFF;"
                    subtopic_label.setToolTip(f"File not found: {subtopic_file_path}")
                subtopic_label.setStyleSheet(style)
                font_metrics = subtopic_label.fontMetrics()
                min_width = font_metrics.boundingRect(missing_subtopic_file).width() + 100
                subtopic_label.setMinimumWidth(min_width)
                max_width = max(max_width, min_width)
                subtopic_label.setWordWrap(False)
                subtopic_label.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred))
                self.file_paths.append(subtopic_file_path)
                subtopic_label.setMouseTracking(True)
                subtopic_label.setCursor(Qt.CursorShape.PointingHandCursor)
                subtopic_label.mousePressEvent = lambda event, fp=subtopic_file_path: self.handle_cell_click(file_path=fp)
                self.main_layout.addWidget(subtopic_label)

            separator = QFrame()
            separator.setMinimumSize(0, 0)
            separator.setFrameShape(QFrame.Shape.NoFrame)
            separator.setStyleSheet("background-color: transparent; border: none; height: 0px;")
            separator.setVisible(False)
            self.main_layout.addWidget(separator)

        self.container.setMinimumWidth(max_width)
        self.container.adjustSize()
        self.container.updateGeometry()
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.update()

    def populate_table_empty_headings(self):
        self.feedback_label.setVisible(False)
        self.table.setVisible(True)
        self.scroll_area.setVisible(False)
        self.table.setRowCount(0)
        self.file_paths = []
        self.href_map = {}
        self.selected_row = None
        table_data = validate_empty_headings(self.ditamap_path)
        if not table_data:
            self.feedback_label.setText("No Empty XMLs Found in the Directory.")
            self.feedback_label.setVisible(True)
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.fix_all_btn.setVisible(False)
            return
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["File Name", "Folder Path", "Action"])
        for row, (file_name, folder_path, file_path, href) in enumerate(table_data):
            self.table.insertRow(row)
            file_item = QTableWidgetItem(file_name)
            file_item.setTextAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            file_item.setToolTip(file_path)
            file_item.setForeground(QColor("#0000FF"))
            font = QFont("Helvetica", 10)
            font.setUnderline(True)
            file_item.setFont(font)
            self.table.setItem(row, 0, file_item)
            folder_display = f"{os.path.basename(folder_path)}/{file_name}"
            folder_item = QTableWidgetItem(folder_display)
            folder_item.setTextAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            folder_item.setToolTip(folder_path)
            folder_item.setForeground(QColor("#0000FF"))
            font = QFont("Helvetica", 10)
            font.setUnderline(True)
            folder_item.setFont(font)
            self.table.setItem(row, 1, folder_item)
            self.file_paths.append(file_path)
            self.href_map[file_path] = href
            fix_btn = QPushButton("Fix")
            fix_btn.setFont(QFont("Helvetica", 9))
            fix_btn.setStyleSheet("background-color: #0D6E6E; color: #FFFFFF; padding: 0px; border-radius: 4px; border: 1px solid #0A5555; min-width: 60px; min-height: 24px; text-align: center;")
            fix_btn.clicked.connect(lambda _, r=row: self.handle_fix_empty_heading(r))
            fix_btn.setMinimumSize(60, 24)
            self.table.setCellWidget(row, 2, fix_btn)
        header = self.table.horizontalHeader()
        table_width = self.table.viewport().width()
        header.setSectionResizeMode(0, header.ResizeMode.Fixed)
        header.setSectionResizeMode(1, header.ResizeMode.Fixed)
        header.setSectionResizeMode(2, header.ResizeMode.Fixed)
        self.table.setColumnWidth(0, int(table_width * 0.4))
        self.table.setColumnWidth(1, int(table_width * 0.4))
        self.table.setColumnWidth(2, int(table_width * 0.2))
        self.table.updateGeometry()
        self._flush_handlers()

    def handle_refresh(self):
        if not self.directory_path and not self.ditamap_path:
            self.feedback_label.setText("No directory or DITA map selected")
            self.table.setVisible(False)
            self.scroll_area.setVisible(False)
            return
        if self.current_mode == "tables":
            self.table.setVisible(True)
            self.scroll_area.setVisible(False)
            self.table.setColumnCount(4)
            self.table.setHorizontalHeaderLabels(["File", "Table Title", "Table Width", "Open"])
            self.fix_all_btn.setVisible(False)
            self.populate_table(validate_tables)
        elif self.current_mode == "graphics":
            self.table.setVisible(True)
            self.scroll_area.setVisible(False)
            self.table.setColumnCount(4)
            self.table.setHorizontalHeaderLabels(["File", "Size Attributes", "Figure Title", "Open"])
            self.fix_all_btn.setVisible(False)
            self.populate_table(validate_graphics)
        elif self.current_mode == "chapter_toc":
            self.table.setVisible(False)
            self.scroll_area.setVisible(True)
            self.fix_all_btn.setVisible(False)
            self.populate_text_list_toc()
        elif self.current_mode == "empty_headings":
            self.table.setVisible(True)
            self.scroll_area.setVisible(False)
            self.fix_all_btn.setVisible(True)
            self.populate_table_empty_headings()
        else:
            self.feedback_label.setText("No check selected")
            self.table.setVisible(False)
            self.scroll_area.setVisible(False)
        self._flush_handlers()