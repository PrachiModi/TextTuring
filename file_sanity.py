from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, QLabel, QFileDialog, QWidget
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QFont, QDesktopServices
from file_numbers import analyze_files, get_files_by_type, move_file_to_trash
from unreferenced_xmls import find_unreferenced_xmls, move_xml_to_trash
from unreferenced_graphics import find_unreferenced_graphics, move_graphic_to_trash
from delete_unnecessary_folder import delete_unnecessary_folders, move_folder_contents_to_trash
import os
from pathlib import Path
import shutil
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

class FileListDialog(QDialog):
    def __init__(self, directory_path: str, file_type: str, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger(__name__)
        self.setWindowTitle(f"Files of Type {file_type}")
        self.setMinimumSize(800, 600)
        self.setModal(True)
        self.directory_path = directory_path
        self.file_type = file_type
        self.parent_widget = parent  # Reference to FileSanityWidget
        self.is_deleting = False

        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        self.setLayout(layout)

        # Table for file list
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["File Name", "Folder Path", "Delete Button"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setFont(QFont("Helvetica", 10))
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, stretch=1)

        # Set dynamic column widths
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        header.setSectionResizeMode(2, header.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 110)

        # Set minimum row height
        self.table.verticalHeader().setDefaultSectionSize(30)

        # Feedback label
        self.feedback_label = QLabel("")
        self.feedback_label.setFont(QFont("Helvetica", 12))
        self.feedback_label.setStyleSheet("color: #FFFFFF;")
        self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.feedback_label)

        # Bottom buttons
        self.bottom_panel = QHBoxLayout()
        self.delete_all_btn = QPushButton("Delete All")
        self.delete_all_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.delete_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF8C00;
                color: #FFFFFF;
                padding: 5px 10px;
                border-radius: 4px;
                border: 1px solid #CC7000;
                min-width: 60px;
                min-height: 24px;
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
        self.back_btn = QPushButton("Back")
        self.back_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.bottom_panel.addWidget(self.delete_all_btn)
        self.bottom_panel.addWidget(self.back_btn)
        layout.addLayout(self.bottom_panel)

        # Apply styling
        self.setStyleSheet("""
            QDialog {
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

        # Connect signals
        self.delete_all_btn.clicked.connect(self.handle_delete_all)
        self.back_btn.clicked.connect(self.accept)

        # Populate table
        self.populate_table()

    def populate_table(self):
        self.logger.debug(f"Populating table for file type: {self.file_type}")
        self.table.setRowCount(0)
        results = get_files_by_type(self.directory_path, self.file_type)
        if not results or (len(results) == 1 and results[0][0] == "Error"):
            self.feedback_label.setText(f"No {self.file_type} files found")
            self.table.setRowCount(1)
            self.table.setItem(0, 0, QTableWidgetItem("No files"))
            self.table.setItem(0, 1, QTableWidgetItem(""))
            self.table.setItem(0, 2, QTableWidgetItem(""))
            self.delete_all_btn.setEnabled(False)
            self.logger.debug(f"No {self.file_type} files found")
        else:
            for row, (file_name, folder_path, action) in enumerate(results):
                self.table.insertRow(row)
                self.table.setItem(row, 0, QTableWidgetItem(file_name))
                self.table.setItem(row, 1, QTableWidgetItem(folder_path))
                self.logger.debug(f"Adding file: {file_name}, Path: {folder_path}, Action: {action}")
                if action == "Delete":
                    delete_btn = QPushButton("Delete")
                    delete_btn.setFont(QFont("Helvetica", 9))
                    delete_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #FF8C00;
                            color: #FFFFFF;
                            padding: 1px 2px;
                            border-radius: 4px;
                            border: 1px solid #CC7000;
                            min-width: 48px;
                            min-height: 18px;
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
                    delete_btn.clicked.connect(lambda _, r=row: self.handle_delete(r))
                    self.table.setCellWidget(row, 2, delete_btn)
                else:
                    self.table.setItem(row, 2, QTableWidgetItem(action))
            self.feedback_label.setText(f"Showing {len(results)} {self.file_type} files")
            self.delete_all_btn.setEnabled(True)
            self.logger.debug(f"Populated table with {len(results)} files")
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(2, max(110, self.table.columnWidth(2)))

    def handle_delete(self, row: int):
        if self.is_deleting:
            return
        self.is_deleting = True
        self.logger.debug(f"Handling delete for row {row}")
        if row < 0 or row >= self.table.rowCount():
            self.feedback_label.setText("Error: Invalid row selected")
            self.is_deleting = False
            self.logger.error("Invalid row selected")
            return
        file_name_item = self.table.item(row, 0)
        folder_path_item = self.table.item(row, 1)
        if not file_name_item or not folder_path_item:
            self.feedback_label.setText("Error: Missing file name or path")
            self.is_deleting = False
            self.logger.error("Missing file name or path")
            return
        file_name = file_name_item.text()
        folder_path = folder_path_item.text()
        for r in range(self.table.rowCount()):
            widget = self.table.cellWidget(r, 2)
            if isinstance(widget, QPushButton):
                widget.setEnabled(False)
        full_path = os.path.join(self.directory_path, folder_path, file_name)
        try:
            move_file_to_trash(full_path, self.directory_path)
            self.table.removeRow(row)
            remaining = self.table.rowCount()
            self.feedback_label.setText(f"Moved {file_name} to LegacyTextTuring. {remaining} files remaining.")
            self.populate_table()
            if remaining == 0:
                self.delete_all_btn.setEnabled(False)
            self.logger.debug(f"Moved {file_name} to LegacyTextTuring, {remaining} files remaining")
        except Exception as e:
            self.feedback_label.setText(f"Failed to move {file_name} to LegacyTextTuring: {str(e)}")
            self.logger.error(f"Failed to move {full_path} to LegacyTextTuring: {str(e)}")
        finally:
            for r in range(self.table.rowCount()):
                widget = self.table.cellWidget(r, 2)
                if isinstance(widget, QPushButton):
                    widget.setEnabled(True)
            self.is_deleting = False

    def handle_delete_all(self):
        self.logger.debug(f"Handling delete all for file type: {self.file_type}")
        results = get_files_by_type(self.directory_path, self.file_type)
        if not results or (len(results) == 1 and results[0][0] == "Error"):
            self.feedback_label.setText(f"No {self.file_type} files to move to LegacyTextTuring")
            self.logger.debug(f"No {self.file_type} files to move to LegacyTextTuring")
            return
        moved_count = 0
        errors = []
        for file_name, folder_path, _ in results:
            full_path = os.path.join(self.directory_path, folder_path, file_name)
            try:
                move_file_to_trash(full_path, self.directory_path)
                moved_count += 1
            except Exception as e:
                errors.append(f"{file_name}: {str(e)}")
                self.logger.error(f"Failed to move {full_path} to LegacyTextTuring: {str(e)}")
        self.table.setRowCount(0)
        self.delete_all_btn.setEnabled(False)
        if errors:
            self.feedback_label.setText(f"Moved {moved_count} files to LegacyTextTuring, {len(errors)} failed: {'; '.join(errors)}")
            self.logger.debug(f"Moved {moved_count} files, {len(errors)} failed: {'; '.join(errors)}")
        else:
            self.feedback_label.setText(f"Successfully moved all {moved_count} {self.file_type} files to LegacyTextTuring")
            self.logger.debug(f"Successfully moved all {moved_count} {self.file_type} files to LegacyTextTuring")

    def accept(self):
        self.logger.debug("Accepting FileListDialog, refreshing parent")
        if self.parent_widget:
            self.parent_widget.refresh_table()
        super().accept()

class FileSanityWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent  # Reference to main window
        self.logger = logging.getLogger(__name__)
        self.directory_path = ""
        self.selected_ditamap = ""
        self.delete_unnecessary_dir = ""
        self.is_deleting = False
        self.current_mode = ""

        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        self.setLayout(layout)

        # Top buttons
        button_panel = QHBoxLayout()
        self.file_analytics_btn = QPushButton("File Analytics")
        self.file_analytics_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.delete_unnecessary_btn = QPushButton("Delete Unnecessary Folders")
        self.delete_unnecessary_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.check_unreferenced_btn = QPushButton("Check Unreferenced XMLs")
        self.check_unreferenced_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.check_unreferenced_graphics_btn = QPushButton("Check Unreferenced Graphics")
        self.check_unreferenced_graphics_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        button_panel.addWidget(self.delete_unnecessary_btn)
        button_panel.addWidget(self.file_analytics_btn)
        button_panel.addWidget(self.check_unreferenced_btn)
        button_panel.addWidget(self.check_unreferenced_graphics_btn)
        layout.addLayout(button_panel)

        # Feedback label
        self.feedback_label = QLabel("Select a check to begin")
        self.feedback_label.setFont(QFont("Helvetica", 14, QFont.Weight.Medium))
        self.feedback_label.setStyleSheet("color: #FFFFFF;")
        self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.feedback_label)

        # Table (initially hidden)
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["File Type", "No. of Files", "Action"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setFont(QFont("Helvetica", 10))
        self.table.setAlternatingRowColors(False)
        self.table.setRowCount(0)
        self.table.setVisible(False)

        # Set dynamic column widths
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        header.setSectionResizeMode(2, header.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 110)
        self.table.verticalHeader().setDefaultSectionSize(30)
        layout.addWidget(self.table, stretch=1)

        # Bottom buttons
        self.bottom_panel = QHBoxLayout()
        self.delete_all_btn = QPushButton("Delete All")
        self.delete_all_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.delete_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF8C00;
                color: #FFFFFF;
                padding: 5px 10px;
                border-radius: 4px;
                border: 1px solid #CC7000;
                min-width: 60px;
                min-height: 24px;
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
        self.delete_all_btn.setVisible(False)
        self.back_btn = QPushButton("Back to Menu")
        self.back_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.bottom_panel.addWidget(self.delete_all_btn)
        self.bottom_panel.addWidget(self.back_btn)
        layout.addLayout(self.bottom_panel)

        # Apply styling
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

        # Connect signals
        self.file_analytics_btn.clicked.connect(self.handle_file_analytics)
        self.delete_unnecessary_btn.clicked.connect(self.handle_delete_directory)
        self.check_unreferenced_btn.clicked.connect(self.handle_check_unreferenced_xmls)
        self.check_unreferenced_graphics_btn.clicked.connect(self.handle_check_unreferenced_graphics)
        self.delete_all_btn.clicked.connect(self.handle_delete_all)
        self.back_btn.clicked.connect(self.parent_window.return_to_main_menu)

    def handle_delete_directory(self):
        self.logger.debug("Handling Delete Unnecessary Folders")
        selected_dir = QFileDialog.getExistingDirectory(self, "Select Directory", "")
        if not selected_dir:
            self.feedback_label.setText("No directory selected")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.logger.debug("No directory selected")
            return
        self.directory_path = selected_dir
        self.current_mode = "delete_unnecessary"
        self.delete_all_btn.setVisible(True)
        self.refresh_delete_directory(selected_dir)

    def handle_file_analytics(self):
        self.logger.debug("Handling File Analytics")
        self.directory_path = QFileDialog.getExistingDirectory(self, "Select Directory", "")
        if not self.directory_path:
            self.feedback_label.setText("No directory selected")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.logger.debug("No directory selected")
            return
        self.current_mode = "file_analytics"
        self.delete_all_btn.setVisible(False)
        self.refresh_table()

    def refresh_table(self):
        self.logger.debug(f"Refreshing table for mode: {self.current_mode}")
        if not self.directory_path:
            self.feedback_label.setText("Select a check to begin")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.logger.debug("No directory selected, showing 'Select a check to begin'")
            return
        self.table.setHorizontalHeaderLabels(["File Type", "No. of Files", "Action"])
        self.table.setRowCount(0)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)
        header.setSectionResizeMode(1, header.ResizeMode.Stretch)
        header.setSectionResizeMode(2, header.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 110)
        try:
            results = analyze_files(self.directory_path)
            if not results:
                self.feedback_label.setText("Select a check to begin")
                self.table.setVisible(False)
                self.feedback_label.setVisible(True)
                self.logger.debug("No files with extensions found, showing 'Select a check to begin'")
            else:
                for row, (file_type, count, action) in enumerate(results):
                    self.table.insertRow(row)
                    self.table.setItem(row, 0, QTableWidgetItem(file_type))
                    self.table.setItem(row, 1, QTableWidgetItem(str(count)))
                    if action == "View":
                        view_btn = QPushButton("View")
                        view_btn.setFont(QFont("Helvetica", 9))
                        view_btn.setStyleSheet("""
                            QPushButton {
                                background-color: #0D6E6E;
                                color: #FFFFFF;
                                padding: 1px 2px;
                                border-radius: 4px;
                                border: 1px solid #0A5555;
                                min-width: 48px;
                                min-height: 18px;
                                text-align: center;
                            }
                            QPushButton:hover {
                                background-color: #139999;
                                border: 1px solid #0C7A7A;
                            }
                        """)
                        view_btn.clicked.connect(lambda _, ft=file_type: self.handle_view(ft))
                        self.table.setCellWidget(row, 2, view_btn)
                    else:
                        self.table.setItem(row, 2, QTableWidgetItem(""))
                total_files = sum(count for _, count, _ in results)
                self.feedback_label.setText(f"Found {total_files} total files")
                self.table.setVisible(True)
                self.feedback_label.setVisible(True)
                self.logger.debug(f"Populated table with {len(results)} rows, {total_files} total files")
            self.table.resizeColumnsToContents()
            self.table.setColumnWidth(2, max(110, self.table.columnWidth(2)))
        except Exception as e:
            self.feedback_label.setText(f"Error: {str(e)}")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.logger.error(f"Error refreshing table: {str(e)}")

    def handle_view(self, file_type: str):
        self.logger.debug(f"Handling view for file type: {file_type}")
        dialog = FileListDialog(self.directory_path, file_type, self)
        dialog.exec()

    def handle_delete_folder(self, row: int, selected_dir: str):
        if self.is_deleting:
            return
        self.is_deleting = True
        self.logger.debug(f"Handling delete folder for row {row}")
        if row < 0 or row >= self.table.rowCount():
            self.feedback_label.setText("Error: Invalid row selected")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.is_deleting = False
            self.logger.error("Invalid row selected")
            return
        folder_name_item = self.table.cellWidget(row, 0)
        folder_path_item = self.table.item(row, 1)
        if not folder_name_item or not folder_path_item:
            self.feedback_label.setText("Error: Missing folder name or path")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.is_deleting = False
            self.logger.error("Missing folder name or path")
            return
        folder_name = folder_name_item.text().split('>')[1].split('<')[0]
        folder_path = folder_path_item.text()
        self.logger.debug(f"Folder name: {folder_name}, Folder path: {folder_path}, Selected dir: {selected_dir}")
        for r in range(self.table.rowCount()):
            widget = self.table.cellWidget(r, 2)
            if isinstance(widget, QPushButton):
                widget.setEnabled(False)
        full_path = os.path.normpath(os.path.join(selected_dir, folder_path))
        self.logger.debug(f"Attempting to move folder to LegacyTextTuring: {full_path}")
        if not os.path.exists(full_path):
            self.feedback_label.setText(f"Error: Folder does not exist: {folder_name}")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.logger.error(f"Folder does not exist: {full_path}")
            self.is_deleting = False
            for r in range(self.table.rowCount()):
                widget = self.table.cellWidget(r, 2)
                if isinstance(widget, QPushButton):
                    widget.setEnabled(True)
            return
        try:
            move_folder_contents_to_trash(full_path, selected_dir)
            self.refresh_delete_directory(selected_dir)
        except Exception as e:
            self.feedback_label.setText(f"Failed to move {folder_name} to LegacyTextTuring: {str(e)}")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.logger.error(f"Failed to move {full_path} to LegacyTextTuring: {str(e)}")
        finally:
            for r in range(self.table.rowCount()):
                widget = self.table.cellWidget(r, 2)
                if isinstance(widget, QPushButton):
                    widget.setEnabled(True)
            self.is_deleting = False

    def handle_delete_directory_all(self, selected_dir: str):
        if self.is_deleting:
            return
        self.is_deleting = True
        self.logger.debug(f"Handling delete all unnecessary folders for selected_dir: {selected_dir}")
        initial_row_count = self.table.rowCount()
        self.logger.debug(f"Initial table row count: {initial_row_count}")
        if initial_row_count == 0:
            self.feedback_label.setText("No folders to move to LegacyTextTuring")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.is_deleting = False
            self.logger.debug("No folders to move to LegacyTextTuring")
            return
        for r in range(self.table.rowCount()):
            widget = self.table.cellWidget(r, 2)
            if isinstance(widget, QPushButton):
                widget.setEnabled(False)
        self.delete_all_btn.setEnabled(False)
        moved_count = 0
        errors = []
        folders_to_delete = []
        # Collect all folders from the table
        for row in range(self.table.rowCount()):
            folder_name_item = self.table.cellWidget(row, 0)
            folder_path_item = self.table.item(row, 1)
            if not folder_name_item or not folder_path_item:
                errors.append(f"Row {row}: Missing folder name or path")
                self.logger.error(f"Row {row}: Missing folder name or path")
                continue
            folder_name = folder_name_item.text().split('>')[1].split('<')[0]
            folder_path = folder_path_item.text()
            full_path = os.path.normpath(os.path.join(selected_dir, folder_path))
            folders_to_delete.append((folder_name, full_path))
            self.logger.debug(f"Row {row}: Added to delete list: {folder_name}, Path: {full_path}")
        # Process each folder
        self.logger.debug(f"Total folders to delete: {len(folders_to_delete)}")
        for folder_name, full_path in folders_to_delete:
            self.logger.debug(f"Attempting to move folder: {folder_name}, Path: {full_path}")
            try:
                if os.path.exists(full_path):
                    move_folder_contents_to_trash(full_path, selected_dir)
                    moved_count += 1
                    self.logger.debug(f"Successfully moved {folder_name} to LegacyTextTuring")
                else:
                    errors.append(f"{folder_name}: Folder does not exist")
                    self.logger.error(f"Folder does not exist: {full_path}")
            except Exception as e:
                errors.append(f"{folder_name}: {str(e)}")
                self.logger.error(f"Failed to move {full_path} to LegacyTextTuring: {str(e)}")
        self.table.setRowCount(0)
        # Update feedback based on results
        if errors:
            self.feedback_label.setText(f"Moved {moved_count} folders to LegacyTextTuring, {len(errors)} failed: {'; '.join(errors)}")
            self.logger.debug(f"Moved {moved_count} folders, {len(errors)} failed: {'; '.join(errors)}")
        else:
            self.feedback_label.setText(f"Successfully moved all {moved_count} folders to LegacyTextTuring")
            self.logger.debug(f"Successfully moved all {moved_count} folders to LegacyTextTuring")
        self.table.setVisible(False)
        self.feedback_label.setVisible(True)
        self.is_deleting = False
        # Refresh table only after all deletions
        self.refresh_delete_directory(selected_dir)
        self.logger.debug(f"Final table row count after deletion: {self.table.rowCount()}")

    def handle_delete_all(self):
        if self.current_mode == "delete_unnecessary":
            self.handle_delete_directory_all(self.directory_path)
        elif self.current_mode in ["unreferenced_xmls", "unreferenced_graphics"]:
            self.handle_delete_all_unreferenced()

    def handle_check_unreferenced_xmls(self):
        self.logger.debug("Handling Check Unreferenced XMLs")
        ditamap_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select your ditamap",
            "",
            "DITA MAP Files (*.ditamap);;All Files (*)"
        )
        if not ditamap_path:
            self.feedback_label.setText("No DITA MAP file selected")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.logger.debug("No DITA MAP file selected")
            return
        self.directory_path = str(Path(ditamap_path).parent)
        self.selected_ditamap = ditamap_path
        self.current_mode = "unreferenced_xmls"
        self.delete_all_btn.setVisible(True)
        self.table.setHorizontalHeaderLabels(["File Name", "Folder Path", "Action"])
        self.table.setRowCount(0)
        try:
            results = find_unreferenced_xmls(self.selected_ditamap, self.directory_path)
            if not results:
                self.feedback_label.setText("No unreferenced XML files found")
                self.table.setVisible(False)
                self.feedback_label.setVisible(True)
                self.delete_all_btn.setEnabled(False)
                self.logger.debug("No unreferenced XML files found")
            else:
                for row, (file_name, folder_path, status) in enumerate(results):
                    self.table.insertRow(row)
                    full_path = os.path.join(self.directory_path, folder_path, file_name)
                    file_url = QUrl.fromLocalFile(full_path).toString()
                    file_link_label = QLabel()
                    file_link_label.setText(f'<a href="{file_url}" style="color: #0000FF; text-decoration: underline;">{file_name}</a>')
                    file_link_label.setStyleSheet("background-color: #FFFFFF;")
                    file_link_label.setOpenExternalLinks(True)
                    file_link_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
                    self.table.setCellWidget(row, 0, file_link_label)
                    folder_full_path = os.path.join(self.directory_path, folder_path)
                    folder_url = QUrl.fromLocalFile(folder_full_path).toString()
                    folder_link_label = QLabel()
                    folder_link_label.setText(f'<a href="{folder_url}" style="color: #0000FF; text-decoration: underline;">{folder_path}</a>')
                    folder_link_label.setStyleSheet("background-color: #FFFFFF;")
                    folder_link_label.setOpenExternalLinks(True)
                    folder_link_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
                    self.table.setCellWidget(row, 1, folder_link_label)
                    delete_btn = QPushButton("Delete")
                    delete_btn.setFont(QFont("Helvetica", 9))
                    delete_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #FF8C00;
                            color: #FFFFFF;
                            padding: 1px 2px;
                            border-radius: 4px;
                            border: 1px solid #CC7000;
                            min-width: 48px;
                            min-height: 18px;
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
                    delete_btn.clicked.connect(lambda _, r=row: self.handle_delete_unreferenced(r))
                    self.table.setCellWidget(row, 2, delete_btn)
                self.feedback_label.setText(f"Found {len(results)} unreferenced XML files")
                self.table.setVisible(True)
                self.feedback_label.setVisible(True)
                self.delete_all_btn.setEnabled(True)
                self.logger.debug(f"Populated table with {len(results)} unreferenced XML files")
        except Exception as e:
            self.feedback_label.setText(f"Error: {str(e)}")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.delete_all_btn.setEnabled(False)
            self.logger.error(f"Error checking unreferenced XMLs: {str(e)}")
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(2, max(110, self.table.columnWidth(2)))

    def handle_check_unreferenced_graphics(self):
        self.logger.debug("Handling Check Unreferenced Graphics")
        ditamap_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select your DITA MAP",
            "",
            "DITA MAP Files (*.ditamap);;All Files (*)"
        )
        if not ditamap_path:
            self.feedback_label.setText("No DITA MAP file selected")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.logger.debug("No DITA MAP file selected")
            return
        self.directory_path = str(Path(ditamap_path).parent)
        self.selected_ditamap = ditamap_path
        self.current_mode = "unreferenced_graphics"
        self.delete_all_btn.setVisible(True)
        self.table.setHorizontalHeaderLabels(["File Name", "Folder Path", "Action"])
        self.table.setRowCount(0)
        try:
            results = find_unreferenced_graphics(self.selected_ditamap, self.directory_path)
            if not results:
                self.feedback_label.setText("No unreferenced graphics files found")
                self.table.setVisible(False)
                self.feedback_label.setVisible(True)
                self.delete_all_btn.setEnabled(False)
                self.logger.debug("No unreferenced graphics files found")
            else:
                for row, (file_name, folder_path, status) in enumerate(results):
                    self.table.insertRow(row)
                    full_path = os.path.join(self.directory_path, folder_path, file_name)
                    file_url = QUrl.fromLocalFile(full_path).toString()
                    file_link_label = QLabel()
                    file_link_label.setText(f'<a href="{file_url}" style="color: #0000FF; text-decoration: underline;">{file_name}</a>')
                    file_link_label.setStyleSheet("background-color: #FFFFFF;")
                    file_link_label.setOpenExternalLinks(True)
                    file_link_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
                    self.table.setCellWidget(row, 0, file_link_label)
                    folder_full_path = os.path.join(self.directory_path, folder_path)
                    folder_url = QUrl.fromLocalFile(folder_full_path).toString()
                    folder_link_label = QLabel()
                    folder_link_label.setText(f'<a href="{folder_url}" style="color: #0000FF; text-decoration: underline;">{folder_path}</a>')
                    folder_link_label.setStyleSheet("background-color: #FFFFFF;")
                    folder_link_label.setOpenExternalLinks(True)
                    folder_link_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
                    self.table.setCellWidget(row, 1, folder_link_label)
                    delete_btn = QPushButton("Delete")
                    delete_btn.setFont(QFont("Helvetica", 9))
                    delete_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #FF8C00;
                            color: #FFFFFF;
                            padding: 1px 2px;
                            border-radius: 4px;
                            border: 1px solid #CC7000;
                            min-width: 48px;
                            min-height: 18px;
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
                    delete_btn.clicked.connect(lambda _, r=row: self.handle_delete_unreferenced_graphic(r))
                    self.table.setCellWidget(row, 2, delete_btn)
                self.feedback_label.setText(f"Found {len(results)} unreferenced graphics files")
                self.table.setVisible(True)
                self.feedback_label.setVisible(True)
                self.delete_all_btn.setEnabled(True)
                self.logger.debug(f"Populated table with {len(results)} unreferenced graphics files")
        except Exception as e:
            self.feedback_label.setText(f"Error: {str(e)}")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.delete_all_btn.setEnabled(False)
            self.logger.error(f"Error checking unreferenced graphics: {str(e)}")
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(2, max(110, self.table.columnWidth(2)))

    def handle_delete_unreferenced(self, row: int):
        if self.is_deleting:
            return
        self.is_deleting = True
        self.logger.debug(f"Handling delete unreferenced XML for row {row}")
        if row < 0 or row >= self.table.rowCount():
            self.feedback_label.setText("Error: Invalid row selected")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.is_deleting = False
            self.logger.error("Invalid row selected")
            return
        file_link_label = self.table.cellWidget(row, 0)
        if not file_link_label:
            self.feedback_label.setText("Error: Missing file name")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.is_deleting = False
            self.logger.error("Missing file name")
            return
        file_name = file_link_label.text().split('>')[1].split('<')[0]
        folder_link_label = self.table.cellWidget(row, 1)
        if not folder_link_label:
            self.feedback_label.setText("Error: Missing path")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.is_deleting = False
            self.logger.error("Missing path")
            return
        folder_path = folder_link_label.text().split('>')[1].split('<')[0]
        for r in range(self.table.rowCount()):
            widget = self.table.cellWidget(r, 2)
            if isinstance(widget, QPushButton):
                widget.setEnabled(False)
        self.delete_all_btn.setEnabled(False)
        full_path = os.path.join(self.directory_path, folder_path, file_name)
        try:
            move_xml_to_trash(full_path, self.directory_path)
            self.table.removeRow(row)
            remaining = self.table.rowCount()
            self.feedback_label.setText(f"Moved {file_name} to LegacyTextTuring. {remaining} files remaining.")
            if self.current_mode == "unreferenced_xmls":
                self.refresh_unreferenced_xmls()
            elif self.current_mode == "unreferenced_graphics":
                self.refresh_unreferenced_graphics()
            self.logger.debug(f"Moved {file_name} to LegacyTextTuring, {remaining} files remaining")
        except Exception as e:
            self.feedback_label.setText(f"Failed to move {file_name} to LegacyTextTuring: {str(e)}")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.logger.error(f"Failed to move {full_path} to LegacyTextTuring: {str(e)}")
        finally:
            for r in range(self.table.rowCount()):
                widget = self.table.cellWidget(r, 2)
                if isinstance(widget, QPushButton):
                    widget.setEnabled(True)
            self.delete_all_btn.setEnabled(self.table.rowCount() > 0)
            self.is_deleting = False

    def handle_delete_unreferenced_graphic(self, row: int):
        if self.is_deleting:
            return
        self.is_deleting = True
        self.logger.debug(f"Handling delete unreferenced graphic for row {row}")
        if row < 0 or row >= self.table.rowCount():
            self.feedback_label.setText("Error: Invalid row selected")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.is_deleting = False
            self.logger.error("Invalid row selected")
            return
        file_link_label = self.table.cellWidget(row, 0)
        if not file_link_label:
            self.feedback_label.setText("Error: Missing file name")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.is_deleting = False
            self.logger.error("Missing file name")
            return
        file_name = file_link_label.text().split('>')[1].split('<')[0]
        folder_link_label = self.table.cellWidget(row, 1)
        if not folder_link_label:
            self.feedback_label.setText("Error: Missing path")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.is_deleting = False
            self.logger.error("Missing path")
            return
        folder_path = folder_link_label.text().split('>')[1].split('<')[0]
        for r in range(self.table.rowCount()):
            widget = self.table.cellWidget(r, 2)
            if isinstance(widget, QPushButton):
                widget.setEnabled(False)
        self.delete_all_btn.setEnabled(False)
        full_path = os.path.join(self.directory_path, folder_path, file_name)
        try:
            move_graphic_to_trash(full_path, self.directory_path)
            self.table.removeRow(row)
            remaining = self.table.rowCount()
            self.feedback_label.setText(f"Moved {file_name} to LegacyTextTuring. {remaining} files remaining.")
            if self.current_mode == "unreferenced_xmls":
                self.refresh_unreferenced_xmls()
            elif self.current_mode == "unreferenced_graphics":
                self.refresh_unreferenced_graphics()
            self.logger.debug(f"Moved {file_name} to LegacyTextTuring, {remaining} files remaining")
        except Exception as e:
            self.feedback_label.setText(f"Failed to move {file_name} to LegacyTextTuring: {str(e)}")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.logger.error(f"Failed to move {full_path} to LegacyTextTuring: {str(e)}")
        finally:
            for r in range(self.table.rowCount()):
                widget = self.table.cellWidget(r, 2)
                if isinstance(widget, QPushButton):
                    widget.setEnabled(True)
            self.delete_all_btn.setEnabled(self.table.rowCount() > 0)
            self.is_deleting = False

    def handle_delete_all_unreferenced(self):
        if self.is_deleting:
            return
        self.is_deleting = True
        self.logger.debug(f"Handling delete all unreferenced for mode: {self.current_mode}")
        if self.table.rowCount() == 0:
            self.feedback_label.setText("No files to move to LegacyTextTuring")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.is_deleting = False
            self.logger.debug("No files to move to LegacyTextTuring")
            return
        for r in range(self.table.rowCount()):
            widget = self.table.cellWidget(r, 2)
            if isinstance(widget, QPushButton):
                widget.setEnabled(False)
        self.delete_all_btn.setEnabled(False)
        moved_count = 0
        errors = []
        files_to_delete = []
        for row in range(self.table.rowCount()):
            file_link_label = self.table.cellWidget(row, 0)
            if not file_link_label:
                errors.append(f"Row {row}: Missing file name")
                continue
            file_name = file_link_label.text().split('>')[1].split('<')[0]
            folder_link_label = self.table.cellWidget(row, 1)
            if not folder_link_label:
                errors.append(f"Row {row}: Missing path")
                continue
            folder_path = folder_link_label.text().split('>')[1].split('<')[0]
            full_path = os.path.join(self.directory_path, folder_path, file_name)
            files_to_delete.append((file_name, full_path))
        trash_function = move_xml_to_trash if self.current_mode == "unreferenced_xmls" else move_graphic_to_trash
        for file_name, full_path in files_to_delete:
            try:
                trash_function(full_path, self.directory_path)
                moved_count += 1
            except Exception as e:
                errors.append(f"{file_name}: {str(e)}")
                self.logger.error(f"Failed to move {full_path} to LegacyTextTuring: {str(e)}")
        self.table.setRowCount(0)
        if errors:
            self.feedback_label.setText(f"Moved {moved_count} files to LegacyTextTuring, {len(errors)} failed: {'; '.join(errors)}")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.logger.debug(f"Moved {moved_count} files, {len(errors)} failed: {'; '.join(errors)}")
        else:
            self.feedback_label.setText(f"Successfully moved all {moved_count} files to LegacyTextTuring")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.logger.debug(f"Successfully moved all {moved_count} files to LegacyTextTuring")
        if self.current_mode == "unreferenced_xmls":
            self.refresh_unreferenced_xmls()
        elif self.current_mode == "unreferenced_graphics":
            self.refresh_unreferenced_graphics()
        self.is_deleting = False

    def refresh_unreferenced_xmls(self):
        self.logger.debug("Refreshing unreferenced XMLs")
        if not self.selected_ditamap or not self.directory_path:
            self.feedback_label.setText("No DITA MAP or directory selected")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.logger.debug("No DITA MAP or directory selected")
            return
        self.current_mode = "unreferenced_xmls"
        self.delete_all_btn.setVisible(True)
        self.table.setHorizontalHeaderLabels(["File Name", "Folder Path", "Action"])
        self.table.setRowCount(0)
        try:
            results = find_unreferenced_xmls(self.selected_ditamap, self.directory_path)
            if not results:
                self.feedback_label.setText("No unreferenced XML files found")
                self.table.setVisible(False)
                self.feedback_label.setVisible(True)
                self.delete_all_btn.setEnabled(False)
                self.logger.debug("No unreferenced XML files found")
            else:
                for row, (file_name, folder_path, status) in enumerate(results):
                    self.table.insertRow(row)
                    full_path = os.path.join(self.directory_path, folder_path, file_name)
                    file_url = QUrl.fromLocalFile(full_path).toString()
                    file_link_label = QLabel()
                    file_link_label.setText(f'<a href="{file_url}" style="color: #0000FF; text-decoration: underline;">{file_name}</a>')
                    file_link_label.setStyleSheet("background-color: #FFFFFF;")
                    file_link_label.setOpenExternalLinks(True)
                    file_link_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
                    self.table.setCellWidget(row, 0, file_link_label)
                    folder_full_path = os.path.join(self.directory_path, folder_path)
                    folder_url = QUrl.fromLocalFile(folder_full_path).toString()
                    folder_link_label = QLabel()
                    folder_link_label.setText(f'<a href="{folder_url}" style="color: #0000FF; text-decoration: underline;">{folder_path}</a>')
                    folder_link_label.setStyleSheet("background-color: #FFFFFF;")
                    folder_link_label.setOpenExternalLinks(True)
                    file_link_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
                    self.table.setCellWidget(row, 1, folder_link_label)
                    delete_btn = QPushButton("Delete")
                    delete_btn.setFont(QFont("Helvetica", 9))
                    delete_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #FF8C00;
                            color: #FFFFFF;
                            padding: 1px 2px;
                            border-radius: 4px;
                            border: 1px solid #CC7000;
                            min-width: 48px;
                            min-height: 18px;
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
                    delete_btn.clicked.connect(lambda _, r=row: self.handle_delete_unreferenced(r))
                    self.table.setCellWidget(row, 2, delete_btn)
                self.feedback_label.setText(f"Found {len(results)} unreferenced XML files")
                self.table.setVisible(True)
                self.feedback_label.setVisible(True)
                self.delete_all_btn.setEnabled(True)
                self.logger.debug(f"Populated table with {len(results)} unreferenced XML files")
        except Exception as e:
            self.feedback_label.setText(f"Error: {str(e)}")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.delete_all_btn.setEnabled(False)
            self.logger.error(f"Error refreshing unreferenced XMLs: {str(e)}")
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(2, max(110, self.table.columnWidth(2)))

    def refresh_unreferenced_graphics(self):
        self.logger.debug("Refreshing unreferenced graphics")
        if not self.selected_ditamap or not self.directory_path:
            self.feedback_label.setText("No DITA MAP or directory selected")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.logger.debug("No DITA MAP or directory selected")
            return
        self.current_mode = "unreferenced_graphics"
        self.delete_all_btn.setVisible(True)
        self.table.setHorizontalHeaderLabels(["File Name", "Folder Path", "Action"])
        self.table.setRowCount(0)
        try:
            results = find_unreferenced_graphics(self.selected_ditamap, self.directory_path)
            if not results:
                self.feedback_label.setText("No unreferenced graphics files found")
                self.table.setVisible(False)
                self.feedback_label.setVisible(True)
                self.delete_all_btn.setEnabled(False)
                self.logger.debug("No unreferenced graphics files found")
            else:
                for row, (file_name, folder_path, status) in enumerate(results):
                    self.table.insertRow(row)
                    full_path = os.path.join(self.directory_path, folder_path, file_name)
                    file_url = QUrl.fromLocalFile(full_path).toString()
                    file_link_label = QLabel()
                    file_link_label.setText(f'<a href="{file_url}" style="color: #0000FF; text-decoration: underline;">{file_name}</a>')
                    file_link_label.setStyleSheet("background-color: #FFFFFF;")
                    file_link_label.setOpenExternalLinks(True)
                    file_link_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
                    self.table.setCellWidget(row, 0, file_link_label)
                    folder_full_path = os.path.join(self.directory_path, folder_path)
                    folder_url = QUrl.fromLocalFile(folder_full_path).toString()
                    folder_link_label = QLabel()
                    folder_link_label.setText(f'<a href="{folder_url}" style="color: #0000FF; text-decoration: underline;">{folder_path}</a>')
                    folder_link_label.setStyleSheet("background-color: #FFFFFF;")
                    folder_link_label.setOpenExternalLinks(True)
                    folder_link_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
                    self.table.setCellWidget(row, 1, folder_link_label)
                    delete_btn = QPushButton("Delete")
                    delete_btn.setFont(QFont("Helvetica", 9))
                    delete_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #FF8C00;
                            color: #FFFFFF;
                            padding: 1px 2px;
                            border-radius: 4px;
                            border: 1px solid #CC7000;
                            min-width: 48px;
                            min-height: 18px;
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
                    delete_btn.clicked.connect(lambda _, r=row: self.handle_delete_unreferenced_graphic(r))
                    self.table.setCellWidget(row, 2, delete_btn)
                self.feedback_label.setText(f"Found {len(results)} unreferenced graphics files")
                self.table.setVisible(True)
                self.feedback_label.setVisible(True)
                self.delete_all_btn.setEnabled(True)
                self.logger.debug(f"Populated table with {len(results)} unreferenced graphics files")
        except Exception as e:
            self.feedback_label.setText(f"Error: {str(e)}")
            self.table.setVisible(False)
            self.feedback_label.setVisible(True)
            self.delete_all_btn.setEnabled(False)
            self.logger.error(f"Error refreshing unreferenced graphics: {str(e)}")
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(2, max(110, self.table.columnWidth(2)))

    def add_table_row(self, col1: str, col2: str, col3: str):
        self.logger.debug(f"Adding table row: {col1}, {col2}, {col3}")
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(col1))
        self.table.setItem(row, 1, QTableWidgetItem(col2))
        self.table.setItem(row, 2, QTableWidgetItem(col3))

    def refresh_delete_directory(self, selected_dir: str):
        self.logger.debug(f"Refreshing delete unnecessary folders with selected_dir: {selected_dir}")
        self.table.setRowCount(0)
        try:
            results = delete_unnecessary_folders(selected_dir)
            if not results:
                self.feedback_label.setText("No Out, Temp, or Empty Folders Found")
                self.table.setVisible(False)
                self.feedback_label.setVisible(True)
                self.delete_all_btn.setEnabled(False)
                self.logger.debug("No out, temp, or empty folders found, showing 'No Out, Temp, or Empty Folders Found'")
            else:
                self.table.setHorizontalHeaderLabels(["Folder Name", "Folder Path", "Action"])
                for row, (folder_name, folder_path, status) in enumerate(results):
                    self.table.insertRow(row)
                    full_path = os.path.join(selected_dir, folder_path)
                    folder_url = QUrl.fromLocalFile(full_path).toString()
                    folder_link_label = QLabel()
                    folder_link_label.setText(f'<a href="{folder_url}" style="color: #0000FF; text-decoration: underline;">{folder_name}</a>')
                    folder_link_label.setStyleSheet("background-color: #FFFFFF;")
                    folder_link_label.setOpenExternalLinks(True)
                    folder_link_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
                    self.table.setCellWidget(row, 0, folder_link_label)
                    self.table.setItem(row, 1, QTableWidgetItem(folder_path))
                    delete_btn = QPushButton("Delete")
                    delete_btn.setFont(QFont("Helvetica", 9))
                    delete_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #FF8C00;
                            color: #FFFFFF;
                            padding: 1px 2px;
                            border-radius: 4px;
                            border: 1px solid #CC7000;
                            min-width: 48px;
                            min-height: 18px;
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
                    delete_btn.clicked.connect(lambda _, r=row, dir=selected_dir: self.handle_delete_folder(r, dir))
                    self.table.setCellWidget(row, 2, delete_btn)
                    self.logger.debug(f"Added table row: Folder Name: {folder_name}, Path: {folder_path}, Full Path: {full_path}")
                self.feedback_label.setText(f"Found {len(results)} Unnecessary Folders")
                self.table.setVisible(True)
                self.delete_all_btn.setEnabled(True)
                self.feedback_label.setVisible(True)
                self.logger.debug(f"Populated table with {len(results)} unnecessary folders")
        except Exception as e:
            self.feedback_label.setText(f"Error: {str(e)}")
            self.table.setVisible(False)
            self.delete_all_btn.setEnabled(False)
            self.feedback_label.setVisible(True)
            self.logger.error(f"Error refreshing delete unnecessary folders: {str(e)}")
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(2, max(110, self.table.columnWidth(2)))