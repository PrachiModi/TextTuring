import logging
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, QLabel, QFileDialog, QMessageBox, QMenu, QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QAction
import os
import platform
import subprocess
from image_border_utils import has_black_border, add_black_border
from non_png_image import scan_non_png_images, convert_to_png
from image_report import scan_images_for_resizing
from file_numbers import move_file_to_trash
from pathlib import Path
import time
import re
from lxml import etree

# Suppress Pillow debug logging
logging.getLogger('PIL').setLevel(logging.INFO)
logger = logging.getLogger(__name__)

class CheckImageSanityWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.image_files = []
        self.directory_path = ""
        self.mode = None

        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        self.setLayout(layout)

        button_panel = QHBoxLayout()
        self.check_borders_btn = QPushButton("Check for Borders")
        self.check_borders_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.check_non_png_btn = QPushButton("Check for Non-PNG Images")
        self.check_non_png_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.check_image_sizes_btn = QPushButton("Check Image Sizes")
        self.check_image_sizes_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        button_panel.addWidget(self.check_borders_btn)
        button_panel.addWidget(self.check_non_png_btn)
        button_panel.addWidget(self.check_image_sizes_btn)
        layout.addLayout(button_panel)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["File Name", "Folder Path", "Reason", "Action"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setFont(QFont("Helvetica", 10))
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        header.setSectionResizeMode(2, header.ResizeMode.Stretch)
        header.setSectionResizeMode(3, header.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 300)
        self.table.setColumnWidth(3, 120)
        self.table.verticalHeader().setDefaultSectionSize(40)

        layout.addWidget(self.table, stretch=1)

        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        self.feedback_label = QLabel("")
        self.feedback_label.setFont(QFont("Helvetica", 12))
        self.feedback_label.setStyleSheet("color: #FFFFFF;")
        self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.feedback_label)

        self.bottom_panel = QHBoxLayout()
        self.add_borders_btn = QPushButton("Add Borders")
        self.add_borders_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.add_borders_btn.setVisible(False)
        self.convert_to_png_btn = QPushButton("Convert to PNG")
        self.convert_to_png_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.convert_to_png_btn.setVisible(False)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.refresh_btn.setVisible(False)
        self.back_btn = QPushButton("Back to Menu")
        self.back_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.bottom_panel.addWidget(self.add_borders_btn)
        self.bottom_panel.addWidget(self.convert_to_png_btn)
        self.bottom_panel.addWidget(self.refresh_btn)
        self.bottom_panel.addWidget(self.back_btn)
        layout.addLayout(self.bottom_panel)

        self.setStyleSheet("""
            QWidget {
                background-color: #1F252A;
            }
            QPushButton {
                background-color: #0D6E6E;
                color: #FFFFFF;
                padding: 10px 20px;
                border-radius: 4px;
                border: 1px solid #0A5555;
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

        self.check_borders_btn.clicked.connect(self.check_borders)
        self.check_non_png_btn.clicked.connect(self.check_non_png_images)
        self.check_image_sizes_btn.clicked.connect(self.check_image_sizes)
        self.add_borders_btn.clicked.connect(self.add_borders)
        self.convert_to_png_btn.clicked.connect(self.convert_to_png)
        self.refresh_btn.clicked.connect(self.refresh_table)
        self.back_btn.clicked.connect(self.parent_window.return_to_main_menu)

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

    def check_borders(self):
        self.mode = "borders"
        self.directory_path = QFileDialog.getExistingDirectory(self, "Select Directory", "")
        if not self.directory_path:
            return
        self.image_files = []
        self.table.setRowCount(0)
        self.feedback_label.setText("")
        self.add_borders_btn.setVisible(False)
        self.convert_to_png_btn.setVisible(False)
        self.refresh_btn.setVisible(False)
        png_found = False
        all_have_borders = True
        for root, dirs, files in os.walk(self.directory_path, topdown=True):
            try:
                for file in files:
                    if file.lower().endswith(".png"):
                        png_found = True
                        file_path = os.path.join(root, file)
                        relative_path = os.path.relpath(root, self.directory_path).replace(os.sep, "/")
                        if relative_path == ".":
                            relative_path = ""
                        else:
                            relative_path += "/"
                        try:
                            has_border, status, reason = has_black_border(file_path)
                            logger.debug(f"Image: {file}, has_border: {has_border}, status: {status}, reason: {reason}")
                            if not has_border:
                                self.image_files.append((file_path, relative_path, status))
                                self.add_table_row(file, relative_path, reason, file_path)
                                all_have_borders = False
                        except Exception as e:
                            logger.error(f"Error processing {file_path}: {str(e)}")
                            self.image_files.append((file_path, relative_path, "Corrupted"))
                            self.add_table_row(file, relative_path, f"Error: {str(e)}", file_path)
                            all_have_borders = False
            except PermissionError:
                continue
        if not png_found:
            self.add_table_row("No PNG images found", "", "", None)
            logger.debug("No PNG images found in directory")
        elif all_have_borders and not self.image_files:
            self.add_table_row("All images have dark borders", "", "", None)
            logger.debug("All images have dark borders")

        logger.debug(f"Table rows: {self.table.rowCount()}")
        for row in range(self.table.rowCount()):
            file_item = self.table.item(row, 0)
            reason_item = self.table.item(row, 2)
            file_text = file_item.text() if file_item else "None"
            reason_text = reason_item.text() if reason_item else "None"
            logger.debug(f"Row {row}: File: {file_text}, Reason: {reason_text}")

        has_border_issues = False
        for row in range(self.table.rowCount()):
            reason_item = self.table.item(row, 2)
            if reason_item and ("missing dark borders" in reason_item.text().lower() or "detected" in reason_item.text().lower()):
                has_border_issues = True
                break
        if self.table.rowCount() > 0:
            has_border_issues = True
        logger.debug(f"has_border_issues: {has_border_issues}, table rows: {self.table.rowCount()}")
        self.add_borders_btn.setVisible(has_border_issues)
        self.refresh_btn.setVisible(True)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(3, 120)

    def check_non_png_images(self):
        self.mode = "non_png"
        self.directory_path = QFileDialog.getExistingDirectory(self, "Select Directory", "")
        if not self.directory_path:
            return
        self.image_files = []
        self.table.setRowCount(0)
        self.feedback_label.setText("")
        self.add_borders_btn.setVisible(False)
        self.convert_to_png_btn.setVisible(False)
        self.refresh_btn.setVisible(False)
        try:
            self.image_files = scan_non_png_images(self.directory_path)
            non_png_found = len(self.image_files) > 0
            for row, (file_path, relative_path, reason) in enumerate(self.image_files):
                file_name = os.path.basename(file_path)
                self.table.insertRow(row)
                self.table.setItem(row, 0, QTableWidgetItem(file_name))
                self.table.setItem(row, 1, QTableWidgetItem(relative_path))
                self.table.setItem(row, 2, QTableWidgetItem(reason))
                delete_btn = QPushButton("Delete")
                delete_btn.setFont(QFont("Helvetica", 9))
                delete_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #FF8C00;
                        color: #FFFFFF;
                        padding: 0px 1px;
                        border-radius: 4px;
                        border: 1px solid #CC7000;
                        min-width: 36px;
                        max-width: 36px;
                        min-height: 16px;
                        text-align: center;
                        margin: 0px;
                    }
                    QPushButton:hover {
                        background-color: #FFA500;
                        border: 1px solid #CC8400;
                    }
                """)
                delete_btn.clicked.connect(lambda checked, r=row: self.handle_delete(r, delete_btn))
                cell_widget = QWidget()
                cell_widget.setObjectName("actionCell")
                cell_layout = QHBoxLayout(cell_widget)
                cell_layout.addWidget(delete_btn)
                cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cell_layout.setContentsMargins(0, 0, 0, 0)
                cell_layout.setSpacing(0)
                self.table.setCellWidget(row, 3, cell_widget)
        except Exception as e:
            logger.error(f"Error scanning directory for non-PNG images: {str(e)}")
            self.add_table_row("Error scanning directory", "", str(e), None)
            non_png_found = False
        if not non_png_found and not self.table.rowCount():
            self.add_table_row("No non-PNG images found", "", "", None)
        has_non_png = len(self.image_files) > 0 and non_png_found
        self.convert_to_png_btn.setVisible(has_non_png)
        self.refresh_btn.setVisible(True)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(3, 120)

    def check_image_sizes(self):
        self.mode = "image_sizes"
        self.directory_path = QFileDialog.getExistingDirectory(self, "Select Directory", "")
        if not self.directory_path:
            return
        logger.debug(f"Checking image sizes in directory: {self.directory_path}")
        self.refresh_image_sizes()

    def refresh_image_sizes(self):
        if not self.directory_path:
            logger.warning("No directory selected for image size check")
            return
        self.image_files = []
        self.table.setRowCount(0)
        self.feedback_label.setText("")
        self.add_borders_btn.setVisible(False)
        self.convert_to_png_btn.setVisible(False)
        self.refresh_btn.setVisible(False)
        try:
            logger.debug("Calling scan_images_for_resizing")
            self.image_files, total_images_scanned, images_to_be_resized = scan_images_for_resizing(self.directory_path)
            logger.debug(f"Found {len(self.image_files)} images to resize, total scanned: {total_images_scanned}")
            for row, (file_path, relative_path, reason) in enumerate(self.image_files):
                file_name = os.path.basename(file_path)
                self.table.insertRow(row)
                self.table.setItem(row, 0, QTableWidgetItem(file_name))
                self.table.setItem(row, 1, QTableWidgetItem(relative_path))
                self.table.setItem(row, 2, QTableWidgetItem(reason))
                fix_size_btn = QPushButton("Fix Size")
                fix_size_btn.setFont(QFont("Helvetica", 9))
                fix_size_btn.setStyleSheet("""
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
                fix_size_btn.clicked.connect(lambda _, r=row: self.handle_fix_size(r))
                cell_widget = QWidget()
                cell_widget.setObjectName("actionCell")
                cell_layout = QHBoxLayout(cell_widget)
                cell_layout.addWidget(fix_size_btn)
                cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cell_layout.setContentsMargins(0, 0, 0, 0)
                cell_layout.setSpacing(0)
                self.table.setCellWidget(row, 3, cell_widget)
        except Exception as e:
            logger.error(f"Error scanning directory for image sizes: {str(e)}")
            self.add_table_row("Error scanning directory", "", str(e), None)
            total_images_scanned = 0
            images_to_be_resized = 0
        if total_images_scanned == 0 and not self.table.rowCount():
            self.add_table_row("No JPEG or PNG images found", "", "", None)
        elif images_to_be_resized == 0 and not self.table.rowCount():
            self.add_table_row("No images need resizing", "", "", None)
        self.feedback_label.setText(f"{images_to_be_resized} Images out of {total_images_scanned} Images need resizing")
        logger.debug(f"Table rows: {self.table.rowCount()}")
        for row in range(self.table.rowCount()):
            file_item = self.table.item(row, 0)
            reason_item = self.table.item(row, 2)
            file_text = file_item.text() if file_item else "None"
            reason_text = reason_item.text() if reason_item else "None"
            logger.debug(f"Row {row}: File: {file_text}, Reason: {reason_text}")
        self.refresh_btn.setVisible(True)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(3, 120)

    def refresh_borders(self):
        if not self.directory_path:
            return
        self.image_files = []
        self.table.setRowCount(0)
        self.feedback_label.setText("")
        self.add_borders_btn.setVisible(False)
        self.convert_to_png_btn.setVisible(False)
        self.refresh_btn.setVisible(False)
        png_found = False
        all_have_borders = True
        for root, dirs, files in os.walk(self.directory_path, topdown=True):
            try:
                for file in files:
                    if file.lower().endswith(".png"):
                        png_found = True
                        file_path = os.path.join(root, file)
                        relative_path = os.path.relpath(root, self.directory_path).replace(os.sep, "/")
                        if relative_path == ".":
                            relative_path = ""
                        else:
                            relative_path += "/"
                        try:
                            has_border, status, reason = has_black_border(file_path)
                            logger.debug(f"Image: {file}, has_border: {has_border}, status: {status}, reason: {reason}")
                            if not has_border:
                                self.image_files.append((file_path, relative_path, status))
                                self.add_table_row(file, relative_path, reason, file_path)
                                all_have_borders = False
                        except Exception as e:
                            logger.error(f"Error processing {file_path}: {str(e)}")
                            self.image_files.append((file_path, relative_path, "Corrupted"))
                            self.add_table_row(file, relative_path, f"Error: {str(e)}", file_path)
                            all_have_borders = False
            except PermissionError:
                continue
        if not png_found:
            self.add_table_row("No PNG images found", "", "", None)
            logger.debug("No PNG images found in directory")
        elif all_have_borders and not self.image_files:
            self.add_table_row("All images have dark borders", "", "", None)
            logger.debug("All images have dark borders")

        logger.debug(f"Table rows: {self.table.rowCount()}")
        for row in range(self.table.rowCount()):
            file_item = self.table.item(row, 0)
            reason_item = self.table.item(row, 2)
            file_text = file_item.text() if file_item else "None"
            reason_text = reason_item.text() if reason_item else "None"
            logger.debug(f"Row {row}: File: {file_text}, Reason: {reason_text}")

        has_border_issues = False
        for row in range(self.table.rowCount()):
            reason_item = self.table.item(row, 2)
            if reason_item and ("missing dark borders" in reason_item.text().lower() or "detected" in reason_item.text().lower()):
                has_border_issues = True
                break
        if self.table.rowCount() > 0:
            has_border_issues = True
        logger.debug(f"has_border_issues: {has_border_issues}, table rows: {self.table.rowCount()}")
        self.add_borders_btn.setVisible(has_border_issues)
        self.refresh_btn.setVisible(True)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(3, 120)

    def handle_fix_size(self, row: int):
        file_path = self.image_files[row][0]
        try:
            system = platform.system()
            if system == "Darwin":
                subprocess.run(["open", file_path], check=True)
            elif system == "Windows":
                subprocess.run(["start", "", file_path], shell=True, check=True)
            elif system == "Linux":
                subprocess.run(["xdg-open", file_path], check=True)
            else:
                self.table.setItem(row, 2, QTableWidgetItem("Error: Unsupported OS"))
        except Exception as e:
            self.table.setItem(row, 2, QTableWidgetItem(f"Error opening file: {str(e)}"))

    def handle_view(self, row: int):
        if row < 0 or row >= len(self.image_files):
            self.feedback_label.setText("Error: Invalid row selected for viewing.")
            print(f"Invalid row {row} in handle_view: image_files length={len(self.image_files)}")
            return
        file_path = self.image_files[row][0]
        file_name = os.path.basename(file_path)
        try:
            system = platform.system()
            if system == "Darwin":
                subprocess.run(["open", file_path], check=True)
            elif system == "Windows":
                subprocess.run(["start", "", file_path], shell=True, check=True)
            elif system == "Linux":
                subprocess.run(["xdg-open", file_path], check=True)
            else:
                self.feedback_label.setText(f"Error: Unsupported OS for viewing {file_name}")
                print(f"Unsupported OS: {system}")
        except Exception as e:
            self.feedback_label.setText(f"Error opening {file_name}: {str(e)}")
            print(f"Error opening {file_path}: {str(e)}")

    def handle_delete(self, row: int, button: QPushButton):
        if row < 0 or row >= len(self.image_files):
            self.feedback_label.setText("Error: Invalid row selected for deletion.")
            print(f"Invalid row {row} in handle_delete: image_files length={len(self.image_files)}")
            return

        file_name = os.path.basename(self.image_files[row][0])
        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to move '{file_name}' to LegacyTextTuring?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        for r in range(self.table.rowCount()):
            widget = self.table.cellWidget(r, 3)
            if isinstance(widget, QWidget):
                btn = widget.layout().itemAt(0).widget()
                if isinstance(btn, QPushButton):
                    btn.setEnabled(False)

        file_path = self.image_files[row][0]
        try:
            parent_dir = str(Path(self.directory_path).parent)
            legacy_folder = os.path.join(parent_dir, "LegacyTextTuring")
            os.makedirs(legacy_folder, exist_ok=True)
            dest_path = os.path.join(legacy_folder, file_name)
            if os.path.exists(dest_path):
                self.feedback_label.setText(f"Error: '{file_name}' already exists in LegacyTextTuring.")
                print(f"File already exists: {dest_path}")
                return

            move_file_to_trash(file_path, parent_dir)
            logging.info(f"Moved {file_path} to {dest_path}")

            self.image_files.pop(row)
            self.table.setRowCount(0)
            for i, (fp, rel_path, reason) in enumerate(self.image_files):
                fname = os.path.basename(fp)
                self.table.insertRow(i)
                self.table.setItem(i, 0, QTableWidgetItem(fname))
                self.table.setItem(i, 1, QTableWidgetItem(rel_path))
                self.table.setItem(i, 2, QTableWidgetItem(reason))
                delete_btn = QPushButton("Delete")
                delete_btn.setFont(QFont("Helvetica", 9))
                delete_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #FF8C00;
                        color: #FFFFFF;
                        padding: 0px 1px;
                        border-radius: 4px;
                        border: 1px solid #CC7000;
                        min-width: 36px;
                        max-width: 36px;
                        min-height: 16px;
                        text-align: center;
                        margin: 0px;
                    }
                    QPushButton:hover {
                        background-color: #FFA500;
                        border: 1px solid #CC8400;
                    }
                """)
                delete_btn.clicked.connect(lambda checked, r=i: self.handle_delete(r, delete_btn))
                cell_widget = QWidget()
                cell_widget.setObjectName("actionCell")
                cell_layout = QHBoxLayout(cell_widget)
                cell_layout.addWidget(delete_btn)
                cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cell_layout.setContentsMargins(0, 0, 0, 0)
                cell_layout.setSpacing(0)
                self.table.setCellWidget(i, 3, cell_widget)
            remaining = len(self.image_files)
            self.feedback_label.setText(f"Moved {file_name} to LegacyTextTuring. {remaining} non-PNG files remaining.")
            if remaining == 0:
                self.convert_to_png_btn.setVisible(False)
                self.table.setRowCount(0)
                self.add_table_row("No non-PNG images found", "", "", None)
        except Exception as e:
            self.feedback_label.setText(f"Failed to move {file_name} to LegacyTextTuring: {str(e)}")
            print(f"Failed to move {file_path} to LegacyTextTuring: {str(e)}")
        finally:
            self.table.resizeColumnsToContents()
            self.table.setColumnWidth(3, 120)

    def refresh_table(self):
        if self.mode == "image_sizes":
            self.refresh_image_sizes()
        elif self.mode == "non_png":
            self.check_non_png_images()
        elif self.mode == "borders":
            self.refresh_borders()

    def update_xml_image_links(self, topics_dir):
        """Scan XML files in Topics directory and update image hrefs from .jpeg/.jpg to .png."""
        updated_files = 0
        try:
            for root, _, files in os.walk(topics_dir):
                for file in files:
                    if file.lower().endswith(".xml"):
                        file_path = os.path.join(root, file)
                        try:
                            # Read XML file
                            parser = etree.XMLParser(remove_blank_text=False)
                            tree = etree.parse(file_path, parser)
                            root_elem = tree.getroot()

                            # Find all image elements with href
                            images = root_elem.xpath("//image[@href]")
                            modified = False
                            for img in images:
                                href = img.get("href")
                                if href and (href.lower().endswith(".jpeg") or href.lower().endswith(".jpg")):
                                    new_href = re.sub(r"\.(jpeg|jpg)$", ".png", href, flags=re.IGNORECASE)
                                    img.set("href", new_href)
                                    modified = True
                                    logger.debug(f"Updated href in {file_path}: {href} -> {new_href}")

                            # Write back if modified
                            if modified:
                                # Preserve original XML declaration and formatting
                                with open(file_path, "wb") as f:
                                    tree.write(f, encoding="utf-8", xml_declaration=True, pretty_print=False)
                                updated_files += 1
                                logger.info(f"Updated image links in {file_path}")
                        except Exception as e:
                            logger.error(f"Error processing XML {file_path}: {str(e)}")
                            continue
        except Exception as e:
            logger.error(f"Error scanning Topics directory {topics_dir}: {str(e)}")
        return updated_files

    def convert_to_png(self):
        images_to_convert = len([img for img in self.image_files if "Converted to PNG" not in img[2] and "Error" not in img[2]])
        if images_to_convert == 0:
            self.feedback_label.setText("No images to convert")
            self.convert_to_png_btn.setVisible(False)
            return
        reply = QMessageBox.question(
            self,
            "Confirm Conversion",
            f"Are you sure you want to convert {images_to_convert} non-PNG images to PNG? Original files will be moved to LegacyTextTuring and XML links will be updated.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        converted_count = 0
        parent_dir = str(Path(self.directory_path).parent)
        for row, (file_path, relative_path, reason) in enumerate(self.image_files[:]):
            if "Converted to PNG" in reason or "Error" in reason:
                continue
            try:
                new_file_path, error = convert_to_png(file_path, parent_dir)
                if error:
                    self.table.setItem(row, 2, QTableWidgetItem(f"Error: {error}"))
                else:
                    new_file_name = os.path.basename(new_file_path)
                    self.table.setItem(row, 0, QTableWidgetItem(new_file_name))
                    self.table.setItem(row, 2, QTableWidgetItem("Converted to PNG"))
                    self.image_files[row] = (new_file_path, relative_path, "Converted to PNG")
                    converted_count += 1
            except Exception as e:
                self.table.setItem(row, 2, QTableWidgetItem(f"Error: {str(e)}"))

        # Update XML files in Topics directory
        topics_dir = os.path.join(parent_dir, "Topics")
        updated_xmls = 0
        if os.path.exists(topics_dir):
            updated_xmls = self.update_xml_image_links(topics_dir)
        else:
            logger.warning(f"Topics directory not found: {topics_dir}")

        self.feedback_label.setText(f"Converted {converted_count} images to PNG, updated {updated_xmls} XML files")
        self.convert_to_png_btn.setVisible(False)
        self.refresh_btn.setVisible(True)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(3, 120)

    def add_borders(self):
        fixed_count = 0
        updated_files = []
        logger.debug(f"Adding borders to {len(self.image_files)} images")
        for row, (file_path, relative_path, reason) in enumerate(self.image_files[:]):
            reason_item = self.table.item(row, 2)
            reason_text = reason_item.text().lower() if reason_item else ""
            logger.debug(f"Processing row {row}: File: {os.path.basename(file_path)}, Reason: {reason_text}")
            if reason_item and ("missing dark borders" in reason_text or "detected" in reason_text):
                try:
                    logger.debug(f"Attempting to add border to {file_path}")
                    success = add_black_border(file_path)
                    if success:
                        logger.debug(f"add_black_border succeeded for {file_path}")
                        try:
                            has_border, new_status, new_reason = has_black_border(file_path)
                            logger.debug(f"Post-border check: has_border: {has_border}, status: {new_status}, reason: {new_reason}")
                            if has_border:
                                fixed_count += 1
                                logger.debug(f"Incremented fixed_count to {fixed_count} for {file_path}")
                            else:
                                updated_files.append((file_path, relative_path, new_status))
                                self.table.setItem(row, 2, QTableWidgetItem(new_reason))
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
                                view_btn.clicked.connect(lambda checked, r=row: self.handle_view(r))
                                cell_widget = QWidget()
                                cell_widget.setObjectName("actionCell")
                                cell_layout = QHBoxLayout(cell_widget)
                                cell_layout.addWidget(view_btn)
                                cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                                cell_layout.setContentsMargins(0, 0, 0, 0)
                                cell_layout.setSpacing(0)
                                self.table.setCellWidget(row, 3, cell_widget)
                        except Exception as e:
                            logger.error(f"Post-border check failed for {file_path}: {str(e)}")
                            self.table.setItem(row, 2, QTableWidgetItem(f"Error: {str(e)}"))
                            self.table.setCellWidget(row, 3, None)
                    else:
                        logger.error(f"add_black_border failed for {file_path}")
                        self.table.setItem(row, 2, QTableWidgetItem("Error: Failed to add border"))
                        self.table.setCellWidget(row, 3, None)
                except Exception as e:
                    logger.error(f"Error adding border to {file_path}: {str(e)}")
                    self.table.setItem(row, 2, QTableWidgetItem(f"Error: {str(e)}"))
                    self.table.setCellWidget(row, 3, None)
            else:
                logger.debug(f"Skipping row {row}: Reason '{reason_text}' does not match criteria")
        self.image_files = updated_files
        self.table.setRowCount(0)
        for i, (file_path, relative_path, status) in enumerate(self.image_files):
            file_name = os.path.basename(file_path)
            try:
                has_border, _, reason = has_black_border(file_path)
            except Exception as e:
                logger.error(f"Error re-checking {file_path}: {str(e)}")
                reason = f"Error: {str(e)}"
            if not has_border:
                self.table.insertRow(i)
                self.table.setItem(i, 0, QTableWidgetItem(file_name))
                self.table.setItem(i, 1, QTableWidgetItem(relative_path))
                self.table.setItem(i, 2, QTableWidgetItem(reason))
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
                view_btn.clicked.connect(lambda checked, r=i: self.handle_view(r))
                cell_widget = QWidget()
                cell_widget.setObjectName("actionCell")
                cell_layout = QHBoxLayout(cell_widget)
                cell_layout.addWidget(view_btn)
                cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cell_layout.setContentsMargins(0, 0, 0, 0)
                cell_layout.setSpacing(0)
                self.table.setCellWidget(i, 3, cell_widget)
        logger.debug(f"Fixed {fixed_count} images, remaining files: {len(self.image_files)}")
        self.feedback_label.setText(f"Fixed {fixed_count} images")
        self.add_borders_btn.setVisible(len(self.image_files) > 0)
        self.refresh_btn.setVisible(True)
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
            view_btn.clicked.connect(lambda checked, r=row: self.handle_view(r))
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