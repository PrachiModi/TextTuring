from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView, QApplication
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QFont, QPalette, QColor, QDesktopServices
import PyPDF2
import os
import subprocess
import json
import time
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class TableCheckThread(QThread):
    progress = pyqtSignal(str)
    update_progress_value = pyqtSignal(int)
    result = pyqtSignal(list)

    def __init__(self, pdf_path):
        super().__init__()
        self.pdf_path = pdf_path
        self.is_canceled = False
        self.total_pages = 0
        self.current_page = 0

    def run(self):
        logger.info(f"Starting TableCheckThread for {self.pdf_path}")
        overflow_pages = []
        try:
            process = subprocess.Popen(
                ["python3", "verify_pdf_tables.py", self.pdf_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            while process.poll() is None:
                line = process.stdout.readline().strip()
                logger.debug(f"Raw stdout line: {line}")
                if line:
                    try:
                        data = json.loads(line)
                        if "progress" in data:
                            self.progress.emit(data["progress"])
                            if "Found" in data["progress"] and "pages" in data["progress"]:
                                try:
                                    self.total_pages = int(data["progress"].split()[1])
                                    logger.info(f"Total pages: {self.total_pages}")
                                except (IndexError, ValueError):
                                    logger.warning("Could not parse total pages")
                            elif "Processing page" in data["progress"]:
                                self.current_page += 1
                                if self.total_pages > 0:
                                    progress = int((self.current_page / self.total_pages) * 100)
                                    self.update_progress_value.emit(progress)
                                    logger.debug(f"Progress: {progress}%")
                        elif "result" in data:
                            overflow_pages = data["result"]
                            logger.info("Received result")
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error: {e} on line: {line}")
                        continue
                if process.poll() is None and self.wait(120000):
                    logger.error("Subprocess timed out after 120 seconds")
                    process.terminate()
                    overflow_pages = ["Error: Validation timed out after 120 seconds"]
                    break
            stdout_remainder = process.stdout.read()
            for line in stdout_remainder.splitlines():
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        if "result" in data:
                            overflow_pages = data["result"]
                            logger.info("Received final result")
                    except json.JSONDecodeError:
                        logger.error(f"JSON decode error on remaining line: {line}")
            stderr_output = process.stderr.read()
            if stderr_output:
                logger.warning(f"Stderr output: {stderr_output}")
                if process.returncode != 0 or not overflow_pages:
                    overflow_pages = [f"Error: {stderr_output}"]
        except Exception as e:
            logger.error(f"Thread exception: {str(e)}")
            overflow_pages = [f"Error calling verify_pdf_tables.py: {str(e)}"]
        if not self.is_canceled:
            self.result.emit(overflow_pages)
            logger.info("TableCheckThread finished")

    def cancel(self):
        self.is_canceled = True
        self.terminate()

class LinkCheckThread(QThread):
    progress = pyqtSignal(str)
    update_progress_value = pyqtSignal(int)
    result = pyqtSignal(dict)

    def __init__(self, pdf_path):
        super().__init__()
        self.pdf_path = pdf_path
        self.is_canceled = False
        self.total_links = 0
        self.current_link = 0

    def run(self):
        logger.info(f"Starting LinkCheckThread for {self.pdf_path}")
        link_report = {}
        try:
            process = subprocess.Popen(
                ["python3", "verify_external_pdf_links.py", self.pdf_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            while process.poll() is None:
                line = process.stdout.readline().strip()
                logger.debug(f"Raw stdout line: {line}")
                if line:
                    try:
                        data = json.loads(line)
                        if "progress" in data:
                            self.progress.emit(data["progress"])
                            if "Found" in data["progress"] and "links" in data["progress"]:
                                try:
                                    self.total_links = int(data["progress"].split()[1])
                                    logger.info(f"Total links: {self.total_links}")
                                except (IndexError, ValueError):
                                    logger.warning("Could not parse total links")
                            elif "Checking link" in data["progress"]:
                                self.current_link += 1
                                if self.total_links > 0:
                                    progress = int((self.current_link / self.total_links) * 100)
                                    self.update_progress_value.emit(progress)
                                    logger.debug(f"Progress: {progress}%")
                        elif "result" in data:
                            link_report = data["result"]
                            logger.info("Received result")
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error: {e} on line: {line}")
                        continue
                if process.poll() is None and self.wait(120000):
                    logger.error("Subprocess timed out after 120 seconds")
                    process.terminate()
                    link_report = {"error": "Validation timed out after 120 seconds"}
                    break
            stdout_remainder = process.stdout.read()
            for line in stdout_remainder.splitlines():
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        if "result" in data:
                            link_report = data["result"]
                            logger.info("Received final result")
                    except json.JSONDecodeError:
                        logger.error(f"JSON decode error on remaining line: {line}")
            stderr_output = process.stderr.read()
            if stderr_output:
                logger.warning(f"Stderr output: {stderr_output}")
                if not link_report:
                    link_report = {"error": f"Error: {stderr_output}"}
        except Exception as e:
            logger.error(f"Thread exception: {str(e)}")
            link_report = {"error": f"Error calling verify_external_pdf_links.py: {str(e)}"}
        if not self.is_canceled:
            self.result.emit(link_report)
            logger.info("LinkCheckThread completed")

    def cancel(self):
        self.is_canceled = True
        self.terminate()

class HTMLValidationThread(QThread):
    progress = pyqtSignal(str)
    folder_status = pyqtSignal(str, str)
    result = pyqtSignal(dict)

    def __init__(self, html_path, mode):
        super().__init__()
        self.html_path = html_path
        self.mode = mode
        self.is_canceled = False

    def run(self):
        logger.info(f"Starting HTMLValidationThread for {self.html_path}, mode={self.mode}")
        html_report = {}
        try:
            process = subprocess.Popen(
                ["python3", "verify_html_content.py", self.html_path, self.mode],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            while process.poll() is None:
                line = process.stdout.readline().strip()
                logger.debug(f"Raw stdout line: {line}")
                if line:
                    try:
                        data = json.loads(line)
                        if "progress" in data:
                            self.progress.emit(data["progress"])
                            if "Processing HTML file" in data["progress"]:
                                try:
                                    file_path = data["progress"].split(": ")[1]
                                    folder_name = os.path.dirname(file_path).split(os.sep)[-1]
                                    self.folder_status.emit(folder_name, "Processing")
                                except (IndexError, ValueError):
                                    logger.warning("Could not parse folder name from progress")
                            elif "Completed processing" in data["progress"]:
                                try:
                                    file_path = data["progress"].split(": ")[1]
                                    folder_name = os.path.dirname(file_path).split(os.sep)[-1]
                                    self.folder_status.emit(folder_name, "Done")
                                except (IndexError, ValueError):
                                    logger.warning("Could not parse folder name for completion")
                        elif "result" in data:
                            html_report = data["result"]
                            logger.info("Received result")
                        elif "error" in data:
                            html_report = {"error": data["error"]}
                            logger.error(f"Error from script: {data['error']}")
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error: {e} on line: {line}")
                        continue
                if process.poll() is None and self.wait(120000):
                    logger.error("Subprocess timed out after 120 seconds")
                    process.terminate()
                    html_report = {"error": "Validation timed out after 120 seconds"}
                    break
            stdout_remainder = process.stdout.read()
            for line in stdout_remainder.splitlines():
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        if "result" in data:
                            html_report = data["result"]
                            logger.info("Received final result")
                        elif "error" in data:
                            html_report = {"error": data["error"]}
                            logger.error(f"Error from script: {data['error']}")
                    except json.JSONDecodeError:
                        logger.error(f"JSON decode error on remaining line: {line}")
            stderr_output = process.stderr.read()
            if stderr_output:
                logger.warning(f"Stderr output from verify_html_content.py: {stderr_output}")
                if not html_report:
                    html_report = {"error": f"Script error: {stderr_output}"}
            if not html_report:
                html_report = {"error": "No valid response received from verify_html_content.py"}
                logger.error("No valid response received")
        except Exception as e:
            logger.error(f"Thread exception: {str(e)}")
            html_report = {"error": f"Thread exception: {str(e)}"}
        if not self.is_canceled:
            self.result.emit(html_report)
            logger.info("HTMLValidationThread finished")

    def cancel(self):
        self.is_canceled = True
        self.terminate()

class ValidateOutputWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent  # Reference to main window
        self.logger = logging.getLogger(__name__)
        self.logger.debug("Initializing ValidateOutputWidget")
        self.pdf_path = None
        self.html_path = None
        self.last_progress_update = 0

        # Set dark frame background
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor("#1F252A"))
        self.setPalette(palette)

        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        self.setLayout(layout)

        # Top button panel
        button_panel = QHBoxLayout()
        button_panel.setSpacing(8)
        button_panel.setContentsMargins(0, 0, 0, 5)

        self.validate_pdf_btn = QPushButton("Validate PDF")
        self.validate_html_btn = QPushButton("Validate HTML")
        for btn in [self.validate_pdf_btn, self.validate_html_btn]:
            btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
            btn.setMinimumSize(150, 30)
            button_panel.addWidget(btn)
        layout.addLayout(button_panel)

        # Middle content area
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background-color: #E6ECEF; border-radius: 4px;")
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(5, 5, 5, 5)
        self.content_layout.setSpacing(0)
        self.content_widget.setLayout(self.content_layout)

        # Feedback label
        self.feedback_label = QLabel("Select a check to begin")
        self.feedback_label.setFont(QFont("Helvetica", 12))
        self.feedback_label.setStyleSheet("color: #121416; background-color: transparent;")
        self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(self.feedback_label, stretch=1)
        layout.addWidget(self.content_widget, stretch=1)

        # Table (initially hidden)
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setFont(QFont("Helvetica", 10))
        self.table.setAlternatingRowColors(True)
        self.table.setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(30)

        # Bottom button panel
        bottom_panel = QHBoxLayout()
        bottom_panel.setSpacing(8)
        bottom_panel.setContentsMargins(0, 5, 0, 0)

        self.back_btn = QPushButton("Back")
        self.back_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.back_btn.setMinimumHeight(30)
        bottom_panel.addWidget(self.back_btn)
        layout.addLayout(bottom_panel)

        # Apply styling
        self.setStyleSheet("""
            QWidget {
                background-color: #1F252A;
            }
            QPushButton {
                background-color: #0D6E6E;
                color: #FFFFFF;
                padding: 5px 15px;
                border-radius: 4px;
                border: 1px solid #0A5555;
                min-height: 20px;
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
                padding: 5px;
            }
            QHeaderView::section {
                background-color: black;
                color: white;
                padding: 4px;
                border: none;
                border-bottom: 1px solid #A0A6A9;
                border-right: 1px solid #A0A6A9;
                font: bold 12px Helvetica;
            }
            QHeaderView::section:last {
                border-right: none;
            }
            QToolTip {
                background-color: #FFFFFF;
                color: #000000;
                border: 1px solid #000000;
                padding: 2px;
            }
        """)

        # Connect signals
        self.validate_pdf_btn.clicked.connect(self.validate_pdf)
        self.validate_html_btn.clicked.connect(self.validate_html)
        self.back_btn.clicked.connect(self.parent_window.return_to_main_menu)

        # Threads for validation
        self.table_check_thread = None
        self.link_check_thread = None
        self.html_validation_thread = None

    def clear_content(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

    def reset_widget(self):
        """Reset the widget to its initial state."""
        self.clear_content()
        self.pdf_path = None
        self.html_path = None
        self.feedback_label.setText("Select a check to begin")
        self.feedback_label.setFont(QFont("Helvetica", 12))
        self.feedback_label.setVisible(True)
        self.table.setVisible(False)
        self.content_layout.addWidget(self.feedback_label, stretch=1)
        self.validate_pdf_btn.setText("Validate PDF")
        self.validate_html_btn.setText("Validate HTML")
        self.validate_pdf_btn.clicked.disconnect()
        self.validate_html_btn.clicked.disconnect()
        self.validate_pdf_btn.clicked.connect(self.validate_pdf)
        self.validate_html_btn.clicked.connect(self.validate_html)
        self.validate_pdf_btn.setEnabled(True)
        self.validate_html_btn.setEnabled(True)
        self.back_btn.clicked.disconnect()
        self.back_btn.clicked.connect(self.parent_window.return_to_main_menu)
        self.back_btn.setEnabled(True)

    def cancel_checks(self):
        if self.table_check_thread and self.table_check_thread.isRunning():
            self.table_check_thread.cancel()
            self.table_check_thread.wait()
        if self.link_check_thread and self.link_check_thread.isRunning():
            self.link_check_thread.cancel()
            self.link_check_thread.wait()
        if self.html_validation_thread and self.html_validation_thread.isRunning():
            self.html_validation_thread.cancel()
            self.html_validation_thread.wait()
        self.feedback_label.setText("Validation canceled")
        self.feedback_label.setVisible(True)
        self.table.setVisible(False)
        self.clear_content()
        self.content_layout.addWidget(self.feedback_label, stretch=1)

    def validate_metadata(self, pdf_path):
        reader = PyPDF2.PdfReader(pdf_path)
        metadata = reader.metadata or {}
        title = metadata.get("/Title", "Unknown")
        author = metadata.get("/Author", "Unknown")
        subject = metadata.get("/Subject", "Unknown")
        keywords = metadata.get("/Keywords", "Unknown")
        title = title.decode("utf-8", errors="ignore") if isinstance(title, bytes) else title
        author = author.decode("utf-8", errors="ignore") if isinstance(author, bytes) else author
        subject = subject.decode("utf-8", errors="ignore") if isinstance(subject, bytes) else subject
        keywords = keywords.decode("utf-8", errors="ignore") if isinstance(keywords, bytes) else keywords
        return {
            "reader": reader,
            "title": title,
            "author": author,
            "subject": subject,
            "keywords": keywords
        }

    def validate_pdf(self):
        self.clear_content()
        self.validate_pdf_btn.setEnabled(False)
        self.validate_html_btn.setEnabled(False)
        pdf_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select PDF File",
            "",
            "PDF Files (*.pdf);;All Files (*)"
        )
        if not pdf_path:
            self.feedback_label.setText("No PDF selected")
            self.feedback_label.setVisible(True)
            self.table.setVisible(False)
            self.content_layout.addWidget(self.feedback_label, stretch=1)
            self.validate_pdf_btn.setText("Validate PDF")
            self.validate_html_btn.setText("Validate HTML")
            self.validate_pdf_btn.clicked.disconnect()
            self.validate_html_btn.clicked.disconnect()
            self.validate_pdf_btn.clicked.connect(self.validate_pdf)
            self.validate_html_btn.clicked.connect(self.validate_html)
            self.back_btn.clicked.disconnect()
            self.back_btn.clicked.connect(self.parent_window.return_to_main_menu)
            self.validate_pdf_btn.setEnabled(True)
            self.validate_html_btn.setEnabled(True)
            return
        try:
            if not os.path.exists(pdf_path):
                self.feedback_label.setText("Error: PDF file does not exist")
                self.feedback_label.setVisible(True)
                self.table.setVisible(False)
                self.content_layout.addWidget(self.feedback_label, stretch=1)
                self.validate_pdf_btn.setText("Validate PDF")
                self.validate_html_btn.setText("Validate HTML")
                self.validate_pdf_btn.clicked.disconnect()
                self.validate_html_btn.clicked.disconnect()
                self.validate_pdf_btn.clicked.connect(self.validate_pdf)
                self.validate_html_btn.clicked.connect(self.validate_html)
                self.back_btn.clicked.disconnect()
                self.back_btn.clicked.connect(self.parent_window.return_to_main_menu)
                self.validate_pdf_btn.setEnabled(True)
                self.validate_html_btn.setEnabled(True)
                return
            file_size_bytes = os.path.getsize(pdf_path)
            file_size_mb = file_size_bytes / (1024 * 1024)
            if file_size_bytes == 0:
                self.feedback_label.setText("Error: PDF file is empty")
                self.feedback_label.setVisible(True)
                self.table.setVisible(False)
                self.content_layout.addWidget(self.feedback_label, stretch=1)
                self.validate_pdf_btn.setText("Validate PDF")
                self.validate_html_btn.setText("Validate HTML")
                self.validate_pdf_btn.clicked.disconnect()
                self.validate_html_btn.clicked.disconnect()
                self.validate_pdf_btn.clicked.connect(self.validate_pdf)
                self.validate_html_btn.clicked.connect(self.validate_html)
                self.back_btn.clicked.disconnect()
                self.back_btn.clicked.connect(self.parent_window.return_to_main_menu)
                self.validate_pdf_btn.setEnabled(True)
                self.validate_html_btn.setEnabled(True)
                return
            metadata_info = self.validate_metadata(pdf_path)
            reader = metadata_info["reader"]
            page_count = len(reader.pages)
            file_name = os.path.basename(pdf_path)
            metadata_lines = [
                f"PDF Metadata:",
                f"File: {file_name}",
                f"Pages: {page_count}, Size: {file_size_mb:.2f} MB",
                f"Title: {metadata_info['title']}",
                f"Author: {metadata_info['author']}",
                f"Subject: {metadata_info['subject']}",
                f"Keywords: {metadata_info['keywords']}"
            ]
            self.feedback_label.setFont(QFont("Helvetica", 12))
            self.feedback_label.setText("\n".join(metadata_lines))
            self.feedback_label.setVisible(True)
            self.table.setVisible(False)
            self.content_layout.addWidget(self.feedback_label, stretch=1)
            self.validate_pdf_btn.setText("Check Links")
            self.validate_html_btn.setText("Check Tables")
            self.validate_pdf_btn.clicked.disconnect()
            self.validate_html_btn.clicked.disconnect()
            self.validate_pdf_btn.clicked.connect(self.check_links)
            self.validate_html_btn.clicked.connect(self.check_tables)
            self.back_btn.clicked.disconnect()
            self.back_btn.clicked.connect(self.reset_widget)
            self.validate_pdf_btn.setEnabled(True)
            self.validate_html_btn.setEnabled(True)
            self.pdf_path = pdf_path
        except PyPDF2.errors.PdfReadError:
            self.feedback_label.setFont(QFont("Helvetica", 12))
            self.feedback_label.setText("Error: Invalid PDF structure")
            self.feedback_label.setVisible(True)
            self.table.setVisible(False)
            self.content_layout.addWidget(self.feedback_label, stretch=1)
            self.validate_pdf_btn.setText("Validate PDF")
            self.validate_html_btn.setText("Validate HTML")
            self.validate_pdf_btn.clicked.disconnect()
            self.validate_html_btn.clicked.disconnect()
            self.validate_pdf_btn.clicked.connect(self.validate_pdf)
            self.validate_html_btn.clicked.connect(self.validate_html)
            self.back_btn.clicked.disconnect()
            self.back_btn.clicked.connect(self.parent_window.return_to_main_menu)
            self.validate_pdf_btn.setEnabled(True)
            self.validate_html_btn.setEnabled(True)
        except PermissionError:
            self.feedback_label.setFont(QFont("Helvetica", 12))
            self.feedback_label.setText("Error: Permission denied accessing PDF")
            self.feedback_label.setVisible(True)
            self.table.setVisible(False)
            self.content_layout.addWidget(self.feedback_label, stretch=1)
            self.validate_pdf_btn.setText("Validate PDF")
            self.validate_html_btn.setText("Validate HTML")
            self.validate_pdf_btn.clicked.disconnect()
            self.validate_html_btn.clicked.disconnect()
            self.validate_pdf_btn.clicked.connect(self.validate_pdf)
            self.validate_html_btn.clicked.connect(self.validate_html)
            self.back_btn.clicked.disconnect()
            self.back_btn.clicked.connect(self.parent_window.return_to_main_menu)
            self.validate_pdf_btn.setEnabled(True)
            self.validate_html_btn.setEnabled(True)
        except Exception as e:
            self.feedback_label.setFont(QFont("Helvetica", 12))
            self.feedback_label.setText(f"Error: Failed to validate PDF: {str(e)}")
            self.feedback_label.setVisible(True)
            self.table.setVisible(False)
            self.content_layout.addWidget(self.feedback_label, stretch=1)
            self.validate_pdf_btn.setText("Validate PDF")
            self.validate_html_btn.setText("Validate HTML")
            self.validate_pdf_btn.clicked.disconnect()
            self.validate_html_btn.clicked.disconnect()
            self.validate_pdf_btn.clicked.connect(self.validate_pdf)
            self.validate_html_btn.clicked.connect(self.validate_html)
            self.back_btn.clicked.disconnect()
            self.back_btn.clicked.connect(self.parent_window.return_to_main_menu)
            self.validate_pdf_btn.setEnabled(True)
            self.validate_html_btn.setEnabled(True)

    def validate_html(self):
        self.clear_content()
        self.validate_pdf_btn.setEnabled(False)
        self.validate_html_btn.setEnabled(False)
        html_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select HTML File (index.html)",
            "",
            "HTML Files (index.html);;All Files (*)"
        )
        if not html_path:
            self.feedback_label.setFont(QFont("Helvetica", 12))
            self.feedback_label.setText("No HTML file selected")
            self.feedback_label.setVisible(True)
            self.table.setVisible(False)
            self.content_layout.addWidget(self.feedback_label, stretch=1)
            self.validate_pdf_btn.setText("Validate PDF")
            self.validate_html_btn.setText("Validate HTML")
            self.validate_pdf_btn.clicked.disconnect()
            self.validate_html_btn.clicked.disconnect()
            self.validate_pdf_btn.clicked.connect(self.validate_pdf)
            self.validate_html_btn.clicked.connect(self.validate_html)
            self.back_btn.clicked.disconnect()
            self.back_btn.clicked.connect(self.parent_window.return_to_main_menu)
            self.validate_pdf_btn.setEnabled(True)
            self.validate_html_btn.setEnabled(True)
            return
        try:
            if not os.path.exists(html_path):
                raise FileNotFoundError("HTML file does not exist")
            file_size_bytes = os.path.getsize(html_path)
            file_size_mb = file_size_bytes / (1024 * 1024)
            if file_size_bytes == 0:
                raise ValueError("HTML file is empty")
            file_name = os.path.basename(html_path)
            self.feedback_label.setFont(QFont("Helvetica", 12))
            self.feedback_label.setText(f"HTML File: {file_name}\nSize: {file_size_mb:.2f} MB")
            self.feedback_label.setVisible(True)
            self.table.setVisible(False)
            self.content_layout.addWidget(self.feedback_label, stretch=1)
            self.validate_pdf_btn.setText("Validate Internal Links")
            self.validate_html_btn.setText("Validate Images")
            self.validate_pdf_btn.clicked.disconnect()
            self.validate_html_btn.clicked.disconnect()
            self.validate_pdf_btn.clicked.connect(self.validate_internal_links)
            self.validate_html_btn.clicked.connect(self.validate_images)
            self.back_btn.clicked.disconnect()
            self.back_btn.clicked.connect(self.reset_widget)
            self.validate_pdf_btn.setEnabled(True)
            self.validate_html_btn.setEnabled(True)
            self.html_path = html_path
        except FileNotFoundError:
            self.feedback_label.setFont(QFont("Helvetica", 12))
            self.feedback_label.setText("Error: HTML file does not exist")
            self.feedback_label.setVisible(True)
            self.table.setVisible(False)
            self.content_layout.addWidget(self.feedback_label, stretch=1)
            self.validate_pdf_btn.setText("Validate PDF")
            self.validate_html_btn.setText("Validate HTML")
            self.validate_pdf_btn.clicked.disconnect()
            self.validate_html_btn.clicked.disconnect()
            self.validate_pdf_btn.clicked.connect(self.validate_pdf)
            self.validate_html_btn.clicked.connect(self.validate_html)
            self.back_btn.clicked.disconnect()
            self.back_btn.clicked.connect(self.parent_window.return_to_main_menu)
            self.validate_pdf_btn.setEnabled(True)
            self.validate_html_btn.setEnabled(True)
        except ValueError:
            self.feedback_label.setFont(QFont("Helvetica", 12))
            self.feedback_label.setText("Error: HTML file is empty")
            self.feedback_label.setVisible(True)
            self.table.setVisible(False)
            self.content_layout.addWidget(self.feedback_label, stretch=1)
            self.validate_pdf_btn.setText("Validate PDF")
            self.validate_html_btn.setText("Validate HTML")
            self.validate_pdf_btn.clicked.disconnect()
            self.validate_html_btn.clicked.disconnect()
            self.validate_pdf_btn.clicked.connect(self.validate_pdf)
            self.validate_html_btn.clicked.connect(self.validate_html)
            self.back_btn.clicked.disconnect()
            self.back_btn.clicked.connect(self.parent_window.return_to_main_menu)
            self.validate_pdf_btn.setEnabled(True)
            self.validate_html_btn.setEnabled(True)
        except Exception as e:
            self.feedback_label.setFont(QFont("Helvetica", 12))
            self.feedback_label.setText(f"Error: Failed to validate HTML: {str(e)}")
            self.feedback_label.setVisible(True)
            self.table.setVisible(False)
            self.content_layout.addWidget(self.feedback_label, stretch=1)
            self.validate_pdf_btn.setText("Validate PDF")
            self.validate_html_btn.setText("Validate HTML")
            self.validate_pdf_btn.clicked.disconnect()
            self.validate_html_btn.clicked.disconnect()
            self.validate_pdf_btn.clicked.connect(self.validate_pdf)
            self.validate_html_btn.clicked.connect(self.validate_html)
            self.back_btn.clicked.disconnect()
            self.back_btn.clicked.connect(self.parent_window.return_to_main_menu)
            self.validate_pdf_btn.setEnabled(True)
            self.validate_html_btn.setEnabled(True)

    def check_tables(self):
        if not self.pdf_path:
            self.feedback_label.setFont(QFont("Helvetica", 12))
            self.feedback_label.setText("Table Check: No PDF selected")
            self.feedback_label.setVisible(True)
            self.table.setVisible(False)
            self.clear_content()
            self.content_layout.addWidget(self.feedback_label, stretch=1)
            return
        self.validate_pdf_btn.setEnabled(False)
        self.validate_html_btn.setEnabled(False)
        self.back_btn.setEnabled(False)
        self.feedback_label.setFont(QFont("Helvetica", 12))
        self.feedback_label.setText("Table Check: Processing...")
        self.feedback_label.setVisible(True)
        self.table.setVisible(False)
        self.clear_content()
        self.content_layout.addWidget(self.feedback_label, stretch=1)
        self.table_check_thread = TableCheckThread(self.pdf_path)
        self.table_check_thread.progress.connect(self.update_table_progress)
        self.table_check_thread.update_progress_value.connect(self.update_table_progress_value)
        self.table_check_thread.result.connect(self.display_table_report)
        self.table_check_thread.start()

    def update_table_progress(self, message):
        current_time = time.time()
        if current_time - self.last_progress_update < 0.5:
            return
        self.last_progress_update = current_time
        self.feedback_label.setFont(QFont("Helvetica", 12))
        self.feedback_label.setText(f"Table Check: {message}")
        self.feedback_label.setVisible(True)
        self.table.setVisible(False)
        self.clear_content()
        self.content_layout.addWidget(self.feedback_label, stretch=1)
        QApplication.processEvents()

    def update_table_progress_value(self, value):
        pass

    def display_table_report(self, overflow_pages):
        self.clear_content()
        self.feedback_label.setFont(QFont("Helvetica", 14, QFont.Weight.Bold))
        if isinstance(overflow_pages, list) and overflow_pages and isinstance(overflow_pages[0], str) and overflow_pages[0].startswith("Error"):
            self.feedback_label.setText(f"Table Check: {overflow_pages[0]}")
        elif overflow_pages:
            overflow_text = "Table Check: Overflowing Tables Detected on Pages:\n" + "\n".join(f"--Page {page}" for page in sorted(overflow_pages, key=lambda x: (x.isdigit(), x)))
            self.feedback_label.setText(overflow_text)
        else:
            self.feedback_label.setText("Table Check: No Overflowing Tables Detected")
        self.feedback_label.setVisible(True)
        self.table.setVisible(False)
        self.content_layout.addWidget(self.feedback_label, stretch=1)
        self.validate_pdf_btn.setEnabled(True)
        self.validate_html_btn.setEnabled(True)
        self.back_btn.setEnabled(True)

    def check_links(self):
        if not self.pdf_path:
            self.feedback_label.setFont(QFont("Helvetica", 12))
            self.feedback_label.setText("Link Report: No PDF selected")
            self.feedback_label.setVisible(True)
            self.table.setVisible(False)
            self.clear_content()
            self.content_layout.addWidget(self.feedback_label, stretch=1)
            return
        self.validate_pdf_btn.setEnabled(False)
        self.validate_html_btn.setEnabled(False)
        self.back_btn.setEnabled(False)
        self.feedback_label.setFont(QFont("Helvetica", 12))
        self.feedback_label.setText("Link Report: Processing...")
        self.feedback_label.setVisible(True)
        self.table.setVisible(False)
        self.clear_content()
        self.content_layout.addWidget(self.feedback_label, stretch=1)
        self.link_check_thread = LinkCheckThread(self.pdf_path)
        self.link_check_thread.progress.connect(self.update_link_progress)
        self.link_check_thread.update_progress_value.connect(self.update_link_progress_value)
        self.link_check_thread.result.connect(self.display_link_report)
        self.link_check_thread.start()

    def update_link_progress(self, message):
        current_time = time.time()
        if current_time - self.last_progress_update < 0.5:
            return
        self.last_progress_update = current_time
        self.feedback_label.setFont(QFont("Helvetica", 12))
        self.feedback_label.setText(f"Link Report: {message}")
        self.feedback_label.setVisible(True)
        self.table.setVisible(False)
        self.clear_content()
        self.content_layout.addWidget(self.feedback_label, stretch=1)
        QApplication.processEvents()

    def update_link_progress_value(self, value):
        pass

    def display_link_report(self, link_report):
        self.clear_content()
        self.feedback_label.setFont(QFont("Helvetica", 12))
        if "error" in link_report:
            self.feedback_label.setText(f"Link Report: {link_report['error']}")
            self.feedback_label.setVisible(True)
            self.table.setVisible(False)
            self.content_layout.addWidget(self.feedback_label, stretch=1)
        elif "total_links" in link_report:
            total_links = link_report["total_links"]
            redirected_links = link_report.get("redirected", [])
            invalid_links = link_report.get("invalid", [])
            unreachable_links = link_report.get("unreachable", [])
            self.feedback_label.setText(f"Link Report: {total_links} Hyperlinks Present.")
            self.feedback_label.setVisible(True)
            self.content_layout.addWidget(self.feedback_label, stretch=0)
            if not redirected_links and not invalid_links and not unreachable_links:
                self.feedback_label.setText(self.feedback_label.text() + "\nAll links are valid with no redirects or errors.")
            else:
                self.table.setRowCount(len(redirected_links) + len(invalid_links) + len(unreachable_links))
                self.table.setColumnCount(4)
                self.table.setHorizontalHeaderLabels(["Page Number", "Link", "Redirector Link", "Status"])
                header = self.table.horizontalHeader()
                header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
                header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
                header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
                header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
                self.table.setWordWrap(True)
                row = 0
                for link in redirected_links:
                    page_numbers = ", ".join(sorted(link['pages'], key=lambda x: (x.isdigit(), x)))
                    self.table.setItem(row, 0, QTableWidgetItem(page_numbers))
                    link_item = QTableWidgetItem(link['url'])
                    link_font = QFont("Helvetica", 12)
                    link_font.setUnderline(True)
                    link_item.setFont(link_font)
                    link_item.setForeground(QColor("#0D6E6E"))
                    link_item.setData(Qt.ItemDataRole.UserRole, link['url'])
                    link_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                    link_item.setToolTip(f"Click to open: {link['url']}")
                    self.table.setItem(row, 1, link_item)
                    redirector_item = QTableWidgetItem(link.get('redirected_to', 'N/A'))
                    if link.get('redirected_to'):
                        redirector_font = QFont("Helvetica", 12)
                        redirector_font.setUnderline(True)
                        redirector_item.setFont(redirector_font)
                        redirector_item.setForeground(QColor("#0D6E6E"))
                        redirector_item.setData(Qt.ItemDataRole.UserRole, link['redirected_to'])
                        redirector_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                        redirector_item.setToolTip(f"Click to open: {link['redirected_to']}")
                    self.table.setItem(row, 2, redirector_item)
                    self.table.setItem(row, 3, QTableWidgetItem(link['reason']))
                    row += 1
                for link in invalid_links:
                    page_numbers = ", ".join(sorted(link['pages'], key=lambda x: (x.isdigit(), x)))
                    self.table.setItem(row, 0, QTableWidgetItem(page_numbers))
                    link_item = QTableWidgetItem(link['url'])
                    link_font = QFont("Helvetica", 12)
                    link_font.setUnderline(True)
                    link_item.setFont(link_font)
                    link_item.setForeground(QColor("#0D6E6E"))
                    link_item.setData(Qt.ItemDataRole.UserRole, link['url'])
                    link_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                    link_item.setToolTip(f"Click to open: {link['url']}")
                    self.table.setItem(row, 1, link_item)
                    self.table.setItem(row, 2, QTableWidgetItem("N/A"))
                    self.table.setItem(row, 3, QTableWidgetItem(link['reason']))
                    row += 1
                for link in unreachable_links:
                    page_numbers = ", ".join(sorted(link['pages'], key=lambda x: (x.isdigit(), x)))
                    self.table.setItem(row, 0, QTableWidgetItem(page_numbers))
                    link_item = QTableWidgetItem(link['url'])
                    link_font = QFont("Helvetica", 12)
                    link_font.setUnderline(True)
                    link_item.setFont(link_font)
                    link_item.setForeground(QColor("#0D6E6E"))
                    link_item.setData(Qt.ItemDataRole.UserRole, link['url'])
                    link_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                    link_item.setToolTip(f"Click to open: {link['url']}")
                    self.table.setItem(row, 1, link_item)
                    self.table.setItem(row, 2, QTableWidgetItem("N/A"))
                    self.table.setItem(row, 3, QTableWidgetItem(link['reason']))
                    row += 1
                self.table.resizeRowsToContents()
                self.table.cellClicked.connect(self.open_url)
                self.table.setVisible(True)
                self.content_layout.addWidget(self.table, stretch=1)
        self.validate_pdf_btn.setEnabled(True)
        self.validate_html_btn.setEnabled(True)
        self.back_btn.setEnabled(True)

    def validate_internal_links(self):
        if not self.html_path:
            self.feedback_label.setFont(QFont("Helvetica", 12))
            self.feedback_label.setText("Internal Links Validation: No HTML file selected")
            self.feedback_label.setVisible(True)
            self.table.setVisible(False)
            self.clear_content()
            self.content_layout.addWidget(self.feedback_label, stretch=1)
            return
        self.validate_pdf_btn.setEnabled(False)
        self.validate_html_btn.setEnabled(False)
        self.back_btn.setEnabled(False)
        self.feedback_label.setFont(QFont("Helvetica", 12))
        self.feedback_label.setText("Internal Links Validation: Processing...")
        self.feedback_label.setVisible(True)
        self.table.setVisible(False)
        self.clear_content()
        self.content_layout.addWidget(self.feedback_label, stretch=1)
        self.html_validation_thread = HTMLValidationThread(self.html_path, "internal_links")
        self.html_validation_thread.progress.connect(self.update_html_progress)
        self.html_validation_thread.folder_status.connect(self.update_folder_status)
        self.html_validation_thread.result.connect(self.display_internal_links_report)
        self.html_validation_thread.start()

    def validate_images(self):
        if not self.html_path:
            self.feedback_label.setFont(QFont("Helvetica", 12))
            self.feedback_label.setText("Images Validation: No HTML file selected")
            self.feedback_label.setVisible(True)
            self.table.setVisible(False)
            self.clear_content()
            self.content_layout.addWidget(self.feedback_label, stretch=1)
            return
        self.validate_pdf_btn.setEnabled(False)
        self.validate_html_btn.setEnabled(False)
        self.back_btn.setEnabled(False)
        self.feedback_label.setFont(QFont("Helvetica", 12))
        self.feedback_label.setText("Images Validation: Processing...")
        self.feedback_label.setVisible(True)
        self.table.setVisible(False)
        self.clear_content()
        self.content_layout.addWidget(self.feedback_label, stretch=1)
        self.html_validation_thread = HTMLValidationThread(self.html_path, "images")
        self.html_validation_thread.progress.connect(self.update_html_progress)
        self.html_validation_thread.folder_status.connect(self.update_folder_status)
        self.html_validation_thread.result.connect(self.display_images_report)
        self.html_validation_thread.start()

    def update_html_progress(self, message):
        current_time = time.time()
        if current_time - self.last_progress_update < 0.5:
            return
        self.last_progress_update = current_time
        self.feedback_label.setFont(QFont("Helvetica", 12))
        self.feedback_label.setText(f"Validation: {message}")
        self.feedback_label.setVisible(True)
        self.table.setVisible(False)
        self.clear_content()
        self.content_layout.addWidget(self.feedback_label, stretch=1)
        QApplication.processEvents()

    def update_folder_status(self, folder_name, status):
        current_time = datetime.now().strftime('%H:%M:%S')
        status_text = f"{folder_name}: {status} ({current_time})"
        self.feedback_label.setFont(QFont("Helvetica", 12))
        self.feedback_label.setText(f"Validation: {status_text}")
        self.feedback_label.setVisible(True)
        self.table.setVisible(False)
        self.clear_content()
        self.content_layout.addWidget(self.feedback_label, stretch=1)
        QApplication.processEvents()

    def display_internal_links_report(self, html_report):
        self.clear_content()
        self.feedback_label.setFont(QFont("Helvetica", 12))
        if "error" in html_report:
            self.feedback_label.setText(f"Internal Links Validation: {html_report['error']}")
            self.feedback_label.setVisible(True)
            self.table.setVisible(False)
            self.content_layout.addWidget(self.feedback_label, stretch=1)
        elif "total_internal_links" in html_report:
            total_links = html_report["total_internal_links"]
            link_issues = html_report.get("link_issues", [])
            self.feedback_label.setText(f"Internal Links Validation: {total_links} Internal Links Found Across All Files.")
            self.feedback_label.setVisible(True)
            self.content_layout.addWidget(self.feedback_label, stretch=0)
            if not link_issues:
                self.feedback_label.setText(self.feedback_label.text() + "\nAll internal links are valid.")
                self.table.setVisible(False)
                self.content_layout.addWidget(self.feedback_label, stretch=1)
            else:
                self.table.setRowCount(len(link_issues))
                self.table.setColumnCount(4)
                self.table.setHorizontalHeaderLabels(["File", "Href", "Location", "Issue"])
                header = self.table.horizontalHeader()
                header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
                header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
                header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
                header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
                self.table.setWordWrap(True)
                for row, issue in enumerate(link_issues):
                    self.table.setItem(row, 0, QTableWidgetItem(os.path.basename(issue["file"])))
                    self.table.setItem(row, 1, QTableWidgetItem(issue["href"]))
                    self.table.setItem(row, 2, QTableWidgetItem(issue["location"]))
                    self.table.setItem(row, 3, QTableWidgetItem(issue["issue"]))
                self.table.resizeRowsToContents()
                self.table.setVisible(True)
                self.content_layout.addWidget(self.table, stretch=1)
        self.validate_pdf_btn.setEnabled(True)
        self.validate_html_btn.setEnabled(True)
        self.back_btn.setEnabled(True)

    def display_images_report(self, html_report):
        self.clear_content()
        self.feedback_label.setFont(QFont("Helvetica", 12))
        if "error" in html_report:
            self.feedback_label.setText(f"Images Validation: {html_report['error']}")
            self.feedback_label.setVisible(True)
            self.table.setVisible(False)
            self.content_layout.addWidget(self.feedback_label, stretch=1)
        elif "total_images" in html_report:
            total_images = html_report["total_images"]
            image_issues = html_report.get("image_issues", [])
            self.feedback_label.setText(f"Images Validation: {total_images} Images Found Across All Files.")
            self.feedback_label.setVisible(True)
            self.content_layout.addWidget(self.feedback_label, stretch=0)
            if total_images == 0:
                self.feedback_label.setText(self.feedback_label.text() + "\nNo images found. This could be because:\n- The HTML files do not contain any <img> tags or background-image CSS properties.\n- Images are embedded using other methods (e.g., JavaScript).\n- The linked files do not exist or are inaccessible.")
                self.table.setVisible(False)
                self.content_layout.addWidget(self.feedback_label, stretch=1)
            elif not image_issues:
                self.feedback_label.setText(self.feedback_label.text() + "\nAll images are accessible.")
                self.table.setVisible(False)
                self.content_layout.addWidget(self.feedback_label, stretch=1)
            else:
                self.table.setRowCount(len(image_issues))
                self.table.setColumnCount(4)
                self.table.setHorizontalHeaderLabels(["File", "Src", "Location", "Issue"])
                header = self.table.horizontalHeader()
                header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
                header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
                header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
                header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
                self.table.setWordWrap(True)
                for row, issue in enumerate(image_issues):
                    self.table.setItem(row, 0, QTableWidgetItem(os.path.basename(issue["file"])))
                    self.table.setItem(row, 1, QTableWidgetItem(issue["src"]))
                    self.table.setItem(row, 2, QTableWidgetItem(issue["location"]))
                    self.table.setItem(row, 3, QTableWidgetItem(issue["issue"]))
                self.table.resizeRowsToContents()
                self.table.setVisible(True)
                self.content_layout.addWidget(self.table, stretch=1)
        self.validate_pdf_btn.setEnabled(True)
        self.validate_html_btn.setEnabled(True)
        self.back_btn.setEnabled(True)

    def open_url(self, row, column):
        if column in (1, 2):
            item = self.table.item(row, column)
            if item:
                url = item.data(Qt.ItemDataRole.UserRole)
                if url and url != "N/A":
                    QDesktopServices.openUrl(QUrl(url))