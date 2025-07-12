from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, QLabel, QFileDialog, QMessageBox, QMenu, QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QAction, QPalette, QColor, QPixmap
import os
import platform
import subprocess
from non_png_image import scan_non_png_images, convert_to_png
from image_report import scan_images_for_resizing
from file_numbers import move_file_to_trash
from markdown_viewer import MarkdownViewer
from pathlib import Path
import time
import re
from lxml import etree
import shutil
from PIL import Image, ImageEnhance, UnidentifiedImageError
import io
import tempfile
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG, filename="image_sanity.log", format="%(asctime)s - %(levelname)s - %(message)s")

class CheckImageSanityWidget(QWidget):
    first_link_update = True
    first_resize = True
    first_conversion = True

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.image_files = []
        self.directory_path = ""
        self.mode = None
        self.button_info_labels = {}
        self.markdown_viewers = []

        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor("#1F252A"))
        self.setPalette(palette)

        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(5)
        self.setLayout(layout)

        button_panel = QHBoxLayout()
        button_panel.setSpacing(8)
        button_panel.setContentsMargins(0, 0, 0, 10)

        check_non_png_layout = QVBoxLayout()
        check_non_png_icon_container = QWidget()
        check_non_png_icon_container.setFixedHeight(40)
        check_non_png_icon_layout = QHBoxLayout()
        check_non_png_icon_container.setLayout(check_non_png_icon_layout)
        check_non_png_icon_container.setStyleSheet("background-color: transparent;")
        check_non_png_info_label = QLabel()
        check_non_png_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio)
            check_non_png_info_label.setPixmap(pixmap)
        else:
            pixmap = QPixmap(16, 16)
            pixmap.fill(Qt.GlobalColor.transparent)
            check_non_png_info_label.setPixmap(pixmap)
        check_non_png_info_label.setStyleSheet("background-color: transparent; border: none;")
        check_non_png_info_label.setCursor(Qt.CursorShape.PointingHandCursor)
        check_non_png_info_label.setVisible(False)
        check_non_png_info_label.mousePressEvent = lambda event: self.open_markdown_help("Check for Non-PNG Images")
        self.button_info_labels["Check for Non-PNG Images"] = check_non_png_info_label
        check_non_png_icon_layout.addWidget(check_non_png_info_label)
        self.check_non_png_btn = QPushButton("Check for Non-PNG Images")
        self.check_non_png_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.check_non_png_btn.setMinimumSize(150, 30)
        self.check_non_png_btn.setStyleSheet("background-color: #0D6E6E; color: #FFFFFF; padding: 5px 10px; border-radius: 4px; border: 1px solid #0A5555;")
        check_non_png_layout.addWidget(check_non_png_icon_container)
        check_non_png_layout.addWidget(self.check_non_png_btn)
        button_panel.addLayout(check_non_png_layout)

        check_image_sizes_layout = QVBoxLayout()
        check_image_sizes_icon_container = QWidget()
        check_image_sizes_icon_container.setFixedHeight(40)
        check_image_sizes_icon_layout = QHBoxLayout()
        check_image_sizes_icon_container.setLayout(check_image_sizes_icon_layout)
        check_image_sizes_icon_container.setStyleSheet("background-color: transparent;")
        check_image_sizes_info_label = QLabel()
        check_image_sizes_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio)
            check_image_sizes_info_label.setPixmap(pixmap)
        else:
            pixmap = QPixmap(16, 16)
            pixmap.fill(Qt.GlobalColor.transparent)
            check_image_sizes_info_label.setPixmap(pixmap)
        check_image_sizes_info_label.setStyleSheet("background-color: transparent; border: none;")
        check_image_sizes_info_label.setCursor(Qt.CursorShape.PointingHandCursor)
        check_image_sizes_info_label.setVisible(False)
        check_image_sizes_info_label.mousePressEvent = lambda event: self.open_markdown_help("Check Image Sizes")
        self.button_info_labels["Check Image Sizes"] = check_image_sizes_info_label
        check_image_sizes_icon_layout.addWidget(check_image_sizes_info_label)
        self.check_image_sizes_btn = QPushButton("Check Image Sizes")
        self.check_image_sizes_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.check_image_sizes_btn.setMinimumSize(150, 30)
        self.check_image_sizes_btn.setStyleSheet("background-color: #0D6E6E; color: #FFFFFF; padding: 5px 10px; border-radius: 4px; border: 1px solid #0A5555;")
        check_image_sizes_layout.addWidget(check_image_sizes_icon_container)
        check_image_sizes_layout.addWidget(self.check_image_sizes_btn)
        button_panel.addLayout(check_image_sizes_layout)

        layout.addLayout(button_panel)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["File Name", "Folder Path", "Reason", "View"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setFont(QFont("Helvetica", 10))
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        header.setSectionResizeMode(2, header.ResizeMode.Stretch)
        header.setSectionResizeMode(3, header.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 120)
        self.table.setVisible(False)
        layout.addWidget(self.table, stretch=1)

        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        self.feedback_label = QLabel("Select a check to begin")
        self.feedback_label.setFont(QFont("Helvetica", 12))
        self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
        self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.feedback_label)

        self.bottom_panel = QHBoxLayout()
        self.bottom_panel.setSpacing(8)

        self.convert_to_png_btn = QPushButton("Convert to PNG")
        self.convert_to_png_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.convert_to_png_btn.setMinimumSize(150, 30)
        self.convert_to_png_btn.setStyleSheet("background-color: #0D6E6E; color: #FFFFFF; padding: 5px 10px; border-radius: 4px; border: 1px solid #0A5555;")
        self.convert_to_png_btn.setVisible(False)
        self.bottom_panel.addWidget(self.convert_to_png_btn)

        self.update_links_btn = QPushButton("Update Links")
        self.update_links_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.update_links_btn.setMinimumSize(150, 30)
        self.update_links_btn.setStyleSheet("background-color: #0D6E6E; color: #FFFFFF; padding: 5px 10px; border-radius: 4px; border: 1px solid #0A5555;")
        self.update_links_btn.setVisible(False)
        self.bottom_panel.addWidget(self.update_links_btn)

        self.fix_image_btn = QPushButton("Fix Images")
        self.fix_image_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.fix_image_btn.setMinimumSize(150, 30)
        self.fix_image_btn.setStyleSheet("background-color: #0D6E6E; color: #FFFFFF; padding: 5px 10px; border-radius: 4px; border: 1px solid #0A5555;")
        self.fix_image_btn.setVisible(False)
        self.bottom_panel.addWidget(self.fix_image_btn)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.refresh_btn.setMinimumSize(150, 30)
        self.refresh_btn.setStyleSheet("background-color: #0D6E6E; color: #FFFFFF; padding: 5px 10px; border-radius: 4px; border: 1px solid #0A5555;")
        self.refresh_btn.setVisible(False)
        self.bottom_panel.addWidget(self.refresh_btn)

        self.back_btn = QPushButton("Back")
        self.back_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.back_btn.setMinimumSize(150, 30)
        self.back_btn.setStyleSheet("background-color: #0D6E6E; color: #FFFFFF; padding: 5px 10px; border-radius: 4px; border: 1px solid #0A5555;")
        self.bottom_panel.addWidget(self.back_btn)

        layout.addLayout(self.bottom_panel)

        self.setStyleSheet("""
            CheckImageSanityWidget, QWidget {
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
                background-color: #4A6A6A;
                color: #A0A0A0;
                border: 1px solid #3A4A4A;
            }
            QTableWidget {
                background-color: #E6ECEF;
                color: #121416;
                border-radius: 4px;
                padding: 5px;
            }
            QTableWidget::item {
                padding: 0px;
                background-color: #E6ECEF;
            }
            QWidget#actionCell {
                background-color: transparent;
            }
        """)
        self.check_non_png_btn.clicked.connect(self.check_non_png_images)
        self.check_image_sizes_btn.clicked.connect(self.check_image_sizes)
        self.convert_to_png_btn.clicked.connect(self.convert_to_png)
        self.update_links_btn.clicked.connect(self.update_links)
        self.fix_image_btn.clicked.connect(self.fix_images)
        self.refresh_btn.clicked.connect(self.refresh_table)
        self.back_btn.clicked.connect(self.return_to_main_menu)

    def return_to_main_menu(self):
        """Handle Back button click by resetting state and returning to main menu."""
        self.reset_state()
        self.parent_window.return_to_main_menu()

    def reset_state(self):
        """Reset widget state to initial conditions."""
        self.image_files = []
        self.directory_path = ""
        self.mode = None
        self.table.setRowCount(0)
        self.table.setVisible(False)
        self.feedback_label.setText("Select a check to begin")
        self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.convert_to_png_btn.setVisible(False)
        self.update_links_btn.setVisible(False)
        self.fix_image_btn.setVisible(False)
        self.refresh_btn.setVisible(False)

    def open_markdown_help(self, button_name):
        """Open the corresponding .md file for the button."""
        md_name = button_name.lower().replace(" ", "_") + ".md"
        md_path = os.path.join(os.path.dirname(__file__), "docs", md_name)
        if not os.path.exists(md_path):
            return
        viewer = MarkdownViewer(md_path, button_name, self.parent_window)
        viewer.show()
        self.markdown_viewers.append(viewer)

    def update_help_ui(self):
        """Show/hide info icons based on parent window's help_enabled state."""
        help_enabled = self.parent_window.help_enabled if self.parent_window else False
        for label in self.button_info_labels.values():
            label.setVisible(help_enabled)

    def show_context_menu(self, position):
        indexes = self.table.selectedIndexes()
        if not indexes:
            return
        menu = QMenu()
        copy_action = QAction("Copy", self)
        copy_action.triggered.connect(self.copy_selected_cell)
        menu.addAction(copy_action)
        menu.exec(self.table.viewport().mapToGlobal(position))

    def copy_selected_cell(self):
        indexes = self.table.selectedIndexes()
        if indexes:
            item = self.table.item(indexes[0].row(), indexes[0].column())
            if item:
                text = item.text()
                clipboard = QApplication.clipboard()
                clipboard.setText(text)
                self.feedback_label.setText(f"Copied: {text[:50]}...")

    def check_non_png_images(self):
        self.mode = "non_png"
        self.directory_path = QFileDialog.getExistingDirectory(self, "Select Directory", "")
        if not self.directory_path:
            return
        self.refresh_non_png_images()

    def refresh_non_png_images(self):
        if not self.directory_path:
            self.reset_state()
            return
        self.image_files = []
        self.table.setRowCount(0)
        self.feedback_label.setText("")
        self.convert_to_png_btn.setVisible(False)
        self.update_links_btn.setVisible(False)
        self.fix_image_btn.setVisible(False)
        self.refresh_btn.setVisible(False)
        try:
            self.image_files = scan_non_png_images(self.directory_path)
            non_png_found = len(self.image_files) > 0
            if not non_png_found:
                self.feedback_label.setText("No Non-PNG Images found")
                self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setVisible(False)
                self.refresh_btn.setVisible(True)
                return
            for row, (file_path, relative_path, reason) in enumerate(self.image_files):
                file_name = os.path.basename(file_path)
                self.add_table_row(file_name, relative_path, reason, file_path)
            self.table.setVisible(True)
            self.convert_to_png_btn.setVisible(True)
            self.refresh_btn.setVisible(True)
        except Exception as e:
            self.feedback_label.setText(f"Error scanning directory: {str(e)}")
            self.add_table_row("Error scanning directory", "", str(e), None)
            non_png_found = False
            self.table.setVisible(True)
            self.refresh_btn.setVisible(True)

    def check_image_sizes(self):
        self.mode = "image_sizes"
        self.directory_path = QFileDialog.getExistingDirectory(self, "Select Directory", "")
        if not self.directory_path:
            return
        self.refresh_image_sizes()

    def refresh_image_sizes(self):
        if not self.directory_path:
            self.reset_state()
            return
        self.image_files = []
        self.table.setRowCount(0)
        self.feedback_label.setText("")
        self.convert_to_png_btn.setVisible(False)
        self.update_links_btn.setVisible(False)
        self.fix_image_btn.setVisible(False)
        self.refresh_btn.setVisible(False)
        try:
            self.image_files, total_images_scanned, images_to_be_resized = scan_images_for_resizing(self.directory_path)
            for row, (file_path, relative_path, reason) in enumerate(self.image_files):
                file_name = os.path.basename(file_path)
                self.add_table_row(file_name, relative_path, reason, file_path)
            self.table.setVisible(True)
            self.feedback_label.setText(f"{images_to_be_resized} Images out of {total_images_scanned} Images need resizing")
            self.fix_image_btn.setVisible(images_to_be_resized > 0)
            self.refresh_btn.setVisible(True)
        except Exception as e:
            self.feedback_label.setText(f"Error scanning directory: {str(e)}")
            self.add_table_row("Error scanning directory", "", str(e), None)
            self.table.setVisible(True)
            self.refresh_btn.setVisible(True)
        if not self.image_files:
            self.feedback_label.setText("No images need resizing")
            self.table.setVisible(False)

    def convert_to_png(self):
        images_to_convert = len([img for img in self.image_files if "Converted to PNG" not in img[2] and "Error" not in img[2]])
        if images_to_convert == 0:
            self.feedback_label.setText("No images to convert")
            self.convert_to_png_btn.setVisible(False)
            self.update_links_btn.setVisible(False)
            return
        reply = QMessageBox.question(
            self,
            "Confirm Conversion",
            f"Are you sure you want to convert {images_to_convert} non-PNG images to PNG? Original files will be moved to LegacyTextTuring/Graphics.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        converted_count = 0
        parent_dir = str(Path(self.directory_path).parent)
        legacy_folder = os.path.join(parent_dir, "LegacyTextTuring")
        graphics_folder = os.path.join(legacy_folder, "Graphics")
        log_file = os.path.join(legacy_folder, "Log.txt")
        os.makedirs(graphics_folder, exist_ok=True)
        new_image_files = self.image_files.copy()  # Create a copy to avoid modifying list during iteration
        for row, (file_path, relative_path, reason) in enumerate(self.image_files):
            if "Converted to PNG" in reason or "Error" in reason:
                continue
            logging.debug(f"Before conversion: row={row}, file_path={file_path}, relative_path={relative_path}, reason={reason}")
            try:
                new_file_path, error = convert_to_png(file_path, parent_dir)
                logging.debug(f"After conversion: file_path={file_path}, new_file_path={new_file_path}, error={error}")
                if error:
                    self.table.setItem(row, 2, QTableWidgetItem(f"Error: {error}"))
                    logging.error(f"Conversion failed for {file_path}: {error}")
                    continue
                if not os.path.exists(new_file_path):
                    self.table.setItem(row, 2, QTableWidgetItem("Error: Converted PNG not found"))
                    logging.error(f"Converted PNG not found: {new_file_path}")
                    continue
                if not os.access(new_file_path, os.R_OK):
                    self.table.setItem(row, 2, QTableWidgetItem("Error: No read permission for PNG"))
                    logging.error(f"No read permission for converted PNG: {new_file_path}")
                    continue
                new_file_name = os.path.basename(new_file_path)
                new_image_files[row] = (new_file_path, relative_path, "Converted to PNG")
                converted_count += 1
                logging.debug(f"Updated image_files[{row}] = {(new_file_path, relative_path, 'Converted to PNG')}")
            except Exception as e:
                self.table.setItem(row, 2, QTableWidgetItem(f"Error: {str(e)}"))
                logging.error(f"Unexpected error during conversion of {file_path}: {str(e)}")
        self.image_files = new_image_files  # Update image_files after all conversions
        # Refresh table to update View button connections
        self.table.setRowCount(0)
        for row, (file_path, relative_path, reason) in enumerate(self.image_files):
            file_name = os.path.basename(file_path)
            self.add_table_row(file_name, relative_path, reason, file_path)
        self.feedback_label.setText(f"Converted {converted_count} images to PNG")
        self.convert_to_png_btn.setVisible(False)
        self.update_links_btn.setVisible(converted_count > 0)
        self.refresh_btn.setVisible(True)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(3, 120)

    def handle_view(self, row: int = None, file_path: str = None):
        if file_path is None:
            if row is None or row < 0 or row >= len(self.image_files):
                self.feedback_label.setText("Error: Invalid row selected for viewing.")
                logging.error(f"Invalid row for viewing: row={row}, image_files length={len(self.image_files)}")
                return
            file_path = self.image_files[row][0]
        logging.debug(f"Attempting to view file: file_path={file_path}")
        file_name = os.path.basename(file_path)
        if not os.path.exists(file_path):
            self.feedback_label.setText(f"Error: File not found: {file_name}")
            logging.error(f"File not found for viewing: {file_path}")
            return
        if not os.access(file_path, os.R_OK):
            self.feedback_label.setText(f"Error: No read permission for {file_name}")
            logging.error(f"No read permission for file: {file_path}")
            return
        try:
            system = platform.system()
            if file_path.lower().endswith(('.xml', '.dita')):
                if system == "Darwin":
                    subprocess.run(["open", file_path], check=True)
                    self.feedback_label.setText(f"Opened XML file: {file_name}")
                elif system == "Windows":
                    subprocess.run(["notepad", file_path], check=True)
                    self.feedback_label.setText(f"Opened XML file: {file_name}")
                elif system == "Linux":
                    subprocess.run(["xdg-open", file_path], check=True)
                    self.feedback_label.setText(f"Opened XML file: {file_name}")
                else:
                    self.feedback_label.setText(f"Error: Unsupported OS for viewing {file_name}")
            else:
                if system == "Darwin":
                    subprocess.run(["open", file_path], check=True)
                    self.feedback_label.setText(f"Opened image: {file_name}")
                elif system == "Windows":
                    subprocess.run(f'start "" "{file_path}"', shell=True, check=True)
                    self.feedback_label.setText(f"Opened image: {file_name}")
                elif system == "Linux":
                    subprocess.run(["xdg-open", file_path], check=True)
                    self.feedback_label.setText(f"Opened image: {file_name}")
                else:
                    self.feedback_label.setText(f"Error: Unsupported OS for viewing {file_name}")
        except subprocess.CalledProcessError as e:
            self.feedback_label.setText(f"Error opening {file_name}: {str(e)}")
            logging.error(f"Subprocess error opening {file_path}: {str(e)}")
        except Exception as e:
            self.feedback_label.setText(f"Error opening {file_name}: {str(e)}")
            logging.error(f"Unexpected error opening {file_path}: {str(e)}")

    def fix_images(self):
        images_to_fix = len(self.image_files)
        if images_to_fix == 0:
            self.feedback_label.setText("No images to fix")
            self.fix_image_btn.setVisible(False)
            return
        reply = QMessageBox.question(
            self,
            "Confirm Fix",
            f"Are you sure you want to fix {images_to_fix} images? Original files will be copied to LegacyTextTuring/Graphics.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        fixed_count = 0
        parent_dir = str(Path(self.directory_path).parent)
        legacy_folder = os.path.join(parent_dir, "LegacyTextTuring")
        graphics_folder = os.path.join(legacy_folder, "Graphics")
        log_file = os.path.join(legacy_folder, "Log.txt")
        os.makedirs(graphics_folder, exist_ok=True)
        for row, (file_path, relative_path, reason) in enumerate(self.image_files[:]):
            temp_path = None
            try:
                file_name = os.path.basename(file_path)
                legacy_path = os.path.join(graphics_folder, file_name)
                if file_path.lower().endswith('.png') and not os.path.exists(legacy_path):
                    shutil.copy2(file_path, legacy_path)
                elif file_path.lower().endswith(('.jpg', '.jpeg')) and not os.path.exists(legacy_path):
                    shutil.copy2(file_path, legacy_path)

                if not os.access(file_path, os.W_OK):
                    raise PermissionError(f"No write permission for {file_path}")

                # Open image without verification
                with Image.open(file_path) as img:
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    width, height = img.size
                    modified = False

                    # Resize if width or height > 1000
                    if width > 1000 or height > 1000:
                        scale = min(999 / width, 999 / height)
                        new_width = int(width * scale)
                        new_height = int(height * scale)
                        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                        img = ImageEnhance.Sharpness(img).enhance(1.5)
                        modified = True

                    # Save to temporary file
                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                        temp_path = temp_file.name
                        img.save(temp_path, format='PNG', compress_level=9)
                        size_mb = os.path.getsize(temp_path) / (1024 * 1024)

                        # Reduce quality if size > 1MB
                        if size_mb > 1:
                            quality = 100
                            while size_mb > 1 and quality >= 10:
                                buffer = io.BytesIO()
                                img.save(buffer, format='PNG', compress_level=9, quality=quality)
                                buffer.seek(0)
                                with open(temp_path, 'wb') as f:
                                    f.write(buffer.getvalue())
                                size_mb = os.path.getsize(temp_path) / (1024 * 1024)
                                quality -= 2
                                modified = True

                    # Move temp file to original path if modified
                    if modified:
                        shutil.move(temp_path, file_path)
                        fixed_count += 1
                        self.table.setItem(row, 2, QTableWidgetItem("Resized"))
                        self.image_files[row] = (file_path, relative_path, "Resized")
                        log_path = relative_path + file_name
                        try:
                            with open(log_file, "a", encoding="utf-8") as f:
                                if CheckImageSanityWidget.first_resize:
                                    f.write("--------------\nImages Resized:\n")
                                    CheckImageSanityWidget.first_resize = False
                                f.write(f"{log_path} - resized\n")
                        except Exception:
                            pass
                    else:
                        os.remove(temp_path)

            except UnidentifiedImageError:
                self.table.setItem(row, 2, QTableWidgetItem("Error: Corrupted image"))
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception as e:
                self.table.setItem(row, 2, QTableWidgetItem(f"Error: {str(e)}"))
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)

        self.feedback_label.setText(f"Fixed {fixed_count} images")
        self.fix_image_btn.setVisible(fixed_count > 0)
        self.refresh_btn.setVisible(True)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(3, 120)

    def update_xml_image_links(self):
        updated_files = 0
        parent_dir = str(Path(self.directory_path).parent)
        legacy_folder = os.path.join(parent_dir, "LegacyTextTuring")
        log_file = os.path.join(legacy_folder, "Log.txt")
        os.makedirs(legacy_folder, exist_ok=True)
        skip_folders = {"legacytextturing", "out", "temp"}
        updated_files_list = []
        for folder_name in ["Topics", "Chapters"]:
            xml_dir = os.path.join(parent_dir, folder_name)
            if not os.path.exists(xml_dir):
                continue
            try:
                for root, _, files in os.walk(xml_dir):
                    if os.path.basename(root).lower() in skip_folders:
                        continue
                    for file in files:
                        if file.lower().endswith((".xml", ".dita")):
                            file_path = os.path.join(root, file)
                            try:
                                parser = etree.XMLParser(remove_blank_text=False)
                                tree = etree.parse(file_path, parser)
                                root_elem = tree.getroot()
                                images = root_elem.xpath("//image[@href]")
                                modified = False
                                for img in images:
                                    href = img.get("href")
                                    if href and (href.lower().endswith(".jpeg") or href.lower().endswith(".jpg")):
                                        new_href = re.sub(r"\.(jpeg|jpg)$", ".png", href, flags=re.IGNORECASE)
                                        img.set("href", new_href)
                                        modified = True
                                if modified:
                                    # Modify the root ID only if hrefs were updated
                                    orig_id = root_elem.get('id')
                                    if orig_id:
                                        new_id = f"ttu_{orig_id}"
                                        root_elem.set('id', new_id)
                                        logging.debug(f"Updated ID from {orig_id} to {new_id} in {file_path}")
                                    rel_path = os.path.relpath(file_path, parent_dir).replace(os.sep, '/')
                                    backup_path = os.path.join(legacy_folder, rel_path)
                                    if not os.path.exists(backup_path):
                                        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                                        shutil.copy2(file_path, backup_path)
                                    with open(file_path, "wb") as f:
                                        tree.write(f, encoding="utf-8", xml_declaration=True, pretty_print=False)
                                    updated_files += 1
                                    updated_files_list.append((file_path, "Link updated"))
                                    try:
                                        with open(log_file, "a", encoding="utf-8") as f:
                                            if CheckImageSanityWidget.first_link_update:
                                                f.write("---------------------------------------------------------------------------\nLinks updated to png:\n")
                                                CheckImageSanityWidget.first_link_update = False
                                            rel_file_path = os.path.relpath(file_path, xml_dir).replace(os.sep, '/')
                                            f.write(f"{folder_name}/{rel_file_path} - Updated link to reference PNG image and modified ID.\n")
                                    except Exception:
                                        pass
                            except Exception:
                                continue
            except Exception:
                pass

        self.table.setRowCount(0)
        if not updated_files_list:
            self.feedback_label.setText("No XML files updated")
            self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setVisible(False)
        else:
            for file_path, reason in updated_files_list:
                file_name = os.path.basename(file_path)
                rel_path = os.path.relpath(os.path.dirname(file_path), self.directory_path).replace(os.sep, '/')
                if rel_path == ".":
                    rel_path = ""
                else:
                    rel_path += "/"
                self.add_table_row(file_name, rel_path, reason, file_path)
            self.table.setVisible(True)
        return updated_files

    def update_links(self):
        if not self.directory_path:
            self.feedback_label.setText("Error: No directory selected.")
            return
        updated_files = self.update_xml_image_links()
        self.feedback_label.setText(f"Updated {updated_files} files with PNG links.")
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(3, 120)

    def add_table_row(self, file_name: str, folder_path: str, reason: str, file_path: str | None):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(file_name))
        self.table.setItem(row, 1, QTableWidgetItem(folder_path))
        reason_item = QTableWidgetItem(reason)
        reason_item.setToolTip(reason)
        self.table.setItem(row, 2, reason_item)
        logging.debug(f"Adding table row: row={row}, file_name={file_name}, folder_path={folder_path}, reason={reason}, file_path={file_path}")
        if file_path:
            view_btn = QPushButton("View")
            view_btn.setFont(QFont("Helvetica", 9))
            view_btn.setStyleSheet("""
                QPushButton {
                    background-color: #007BFF;
                    color: #FFFFFF;
                    padding: 0px 1px;
                    border-radius: 4px;
                    border: 1px solid #0056B3;
                    min-width: 36px;
                    max-width: 36px;
                    min-height: 16px;
                    text-align: center;
                    margin: 0px;
                }
                QPushButton:hover {
                    background-color: #0056B3;
                    border: 1px solid #003087;
                }
            """)
            view_btn.clicked.connect(lambda checked, fp=file_path: self.handle_view(file_path=fp))
            cell_widget = QWidget()
            cell_widget.setObjectName("actionCell")
            cell_layout = QHBoxLayout(cell_widget)
            cell_layout.addWidget(view_btn)
            cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(0)
            self.table.setCellWidget(row, 3, cell_widget)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(3, 120)

    def refresh_table(self):
        if self.mode == "image_sizes":
            self.refresh_image_sizes()
        elif self.mode == "non_png":
            self.refresh_non_png_images()