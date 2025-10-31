from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView, QApplication
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QFont, QPalette, QColor, QDesktopServices, QPixmap
import PyPDF2
import os
import subprocess
import json
from pathlib import Path
from markdown_viewer import MarkdownViewer
import sys
import time

class TableCheckThread(QThread):
    result = pyqtSignal(list)
    progress = pyqtSignal(str)

    def __init__(self, pdf_path):
        super().__init__()
        self.pdf_path = pdf_path
        self.is_canceled = False
        self.process = None

    def run(self):
        overflow_pages = []
        try:
            python_path = sys.executable
            print(f"TableCheckThread: Using Python executable: {python_path}", flush=True)
            result = subprocess.run([python_path, "-c", "import fitz; print('PyMuPDF installed')"], capture_output=True, text=True)
            print(f"TableCheckThread: PyMuPDF check: {result.stdout.strip() or result.stderr.strip()}", flush=True)

            self.process = subprocess.Popen(
                [python_path, "verify_pdf_tables.py", self.pdf_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
                env={"PYTHONUNBUFFERED": "1"}
            )
            while self.process.poll() is None and not self.is_canceled:
                line = self.process.stdout.readline().strip()
                if line:
                    print(f"TableCheckThread: Received line: {line}", flush=True)
                    if line.startswith("Progress:"):
                        self.progress.emit(line)
                    elif line.startswith("{"):
                        try:
                            data = json.loads(line)
                            print(f"TableCheckThread: Parsed JSON: {data}", flush=True)
                            if "result" in data:
                                overflow_pages = data["result"]
                            elif "error" in data:
                                overflow_pages = [f"Error: {data['error']}"]
                        except json.JSONDecodeError as e:
                            print(f"TableCheckThread: JSON decode error: {str(e)}", flush=True)
            stderr = self.process.stderr.read().strip()
            if stderr and not self.is_canceled:
                print(f"TableCheckThread: stderr: {stderr}", flush=True)
                if not overflow_pages:
                    overflow_pages = [f"Error: {stderr}"]
            if not overflow_pages and not self.is_canceled:
                overflow_pages = []
        except subprocess.TimeoutExpired:
            if self.process:
                self.process.terminate()
            overflow_pages = ["Error: Validation timed out"]
            print(f"TableCheckThread: Timeout error: {overflow_pages}", flush=True)
        except Exception as e:
            overflow_pages = [f"Error calling verify_pdf_tables.py: {str(e)}"]
            print(f"TableCheckThread: Exception: {overflow_pages}", flush=True)
        if not self.is_canceled:
            print(f"TableCheckThread: Emitting result: {overflow_pages}", flush=True)
            self.result.emit(overflow_pages)

    def cancel(self):
        self.is_canceled = True
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.terminate()
        self.wait()
        print(f"TableCheckThread: Canceled", flush=True)

class LinkCheckThread(QThread):
    result = pyqtSignal(dict)
    progress = pyqtSignal(str)

    def __init__(self, pdf_path):
        super().__init__()
        self.pdf_path = pdf_path
        self.is_canceled = False
        self.process = None
        self.script_dir = os.path.dirname(os.path.abspath(__file__))

    def run(self):
        link_report = {}
        stdout_lines = []
        try:
            python_path = sys.executable
            print(f"LinkCheckThread: Using Python executable: {python_path}", flush=True)
            print(f"LinkCheckThread: Working directory: {self.script_dir}", flush=True)
            result = subprocess.run([python_path, "-c", "import fitz; print('PyMuPDF installed')"], capture_output=True, text=True, timeout=5)
            print(f"LinkCheckThread: PyMuPDF check: {result.stdout.strip() or result.stderr.strip()}", flush=True)

            self.process = subprocess.Popen(
                [python_path, "validate_external_pdf_links.py", self.pdf_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=8192,
                universal_newlines=True,
                env={"PYTHONUNBUFFERED": "1"},
                cwd=self.script_dir
            )
            timeout = 1200  # 20-minute timeout
            start_time = time.time()
            while self.process.poll() is None and not self.is_canceled and (time.time() - start_time) < timeout:
                try:
                    line = self.process.stdout.readline().strip()
                    if line:
                        print(f"LinkCheckThread: Received line: {line}", flush=True)
                        stdout_lines.append(line)
                        if line.startswith("Progress:"):
                            self.progress.emit(line)
                except UnicodeDecodeError as e:
                    print(f"LinkCheckThread: Unicode decode error: {str(e)}", flush=True)
            stderr = self.process.stderr.read().strip()
            if stderr and not self.is_canceled:
                print(f"LinkCheckThread: stderr: {stderr}", flush=True)
            return_code = self.process.poll()
            print(f"LinkCheckThread: Subprocess return code: {return_code}", flush=True)
            # Try parsing accumulated stdout lines
            for line in stdout_lines:
                if line.startswith("{"):
                    try:
                        data = json.loads(line)
                        print(f"LinkCheckThread: Parsed JSON: {data}", flush=True)
                        if "result" in data:
                            link_report = data
                        elif "error" in data:
                            link_report = {"error": data["error"]}
                        break
                    except json.JSONDecodeError as e:
                        print(f"LinkCheckThread: JSON decode error: {str(e)}", flush=True)
            # Fallback to JSON files
            if not link_report and not self.is_canceled:
                for _ in range(5):  # Retry 5 times
                    partial_file = os.path.join(self.script_dir, 'validation_result_partial.json')
                    result_file = os.path.join(self.script_dir, 'validation_result.json')
                    if os.path.exists(partial_file):
                        try:
                            with open(partial_file, 'r', encoding='utf-8') as f:
                                partial_data = json.load(f)
                                print(f"LinkCheckThread: Loaded partial result: {partial_data}", flush=True)
                                if "partial_result" in partial_data:
                                    link_report = {"result": partial_data["partial_result"]}
                                    break
                        except (json.JSONDecodeError, OSError) as e:
                            print(f"LinkCheckThread: Error reading {partial_file}: {str(e)}", flush=True)
                    if os.path.exists(result_file):
                        try:
                            with open(result_file, 'r', encoding='utf-8') as f:
                                link_report = json.load(f)
                                print(f"LinkCheckThread: Loaded result from {result_file}: {link_report}", flush=True)
                                break
                        except (json.JSONDecodeError, OSError) as e:
                            print(f"LinkCheckThread: Error reading {result_file}: {str(e)}", flush=True)
                    time.sleep(2)  # Longer delay for file writes
                if not link_report:
                    link_report = {"error": f"No valid JSON response received and no fallback file found (checked {partial_file}, {result_file})"}
            if not self.is_canceled:
                print(f"LinkCheckThread: Emitting result: {link_report}", flush=True)
                self.result.emit(link_report)
        except subprocess.TimeoutExpired:
            if self.process:
                self.process.terminate()
                try:
                    self.process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.process.kill()
            link_report = {"error": "Validation timed out"}
            print(f"LinkCheckThread: Timeout error: {link_report}", flush=True)
            self.result.emit(link_report)
        except Exception as e:
            link_report = {"error": f"Error calling validate_external_pdf_links.py: {str(e)}"}
            print(f"LinkCheckThread: Exception: {link_report}", flush=True)
            self.result.emit(link_report)
        finally:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.process.kill()
            print(f"LinkCheckThread: Subprocess cleaned up", flush=True)

    def cancel(self):
        self.is_canceled = True
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.terminate()
        self.wait()
        print(f"LinkCheckThread: Canceled", flush=True)
        
class HTMLValidationThread(QThread):
    result = pyqtSignal(dict)
    progress = pyqtSignal(str)

    def __init__(self, html_path, mode):
        super().__init__()
        self.html_path = html_path
        self.mode = mode
        self.is_canceled = False
        self.process = None

    def run(self):
        html_report = {}
        try:
            script_path = os.path.abspath("verify_html_content.py")
            if not os.path.exists(script_path):
                raise FileNotFoundError(f"verify_html_content.py not found at {script_path}")
            python_path = sys.executable
            print(f"HTMLValidationThread: Using Python executable: {python_path}", flush=True)
            result = subprocess.run([python_path, "-c", "import fitz; print('PyMuPDF installed')"], capture_output=True, text=True)
            print(f"HTMLValidationThread: PyMuPDF check: {result.stdout.strip() or result.stderr.strip()}", flush=True)

            self.process = subprocess.Popen(
                [python_path, script_path, self.html_path, self.mode],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
                env={"PYTHONUNBUFFERED": "1"}
            )
            stdout_lines = []
            while self.process.poll() is None and not self.is_canceled:
                line = self.process.stdout.readline().strip()
                if line:
                    print(f"HTMLValidationThread: Received line: {line}", flush=True)
                    if line.startswith("Progress:"):
                        self.progress.emit(line)
                    elif line.startswith("{"):
                        stdout_lines.append(line)
                        try:
                            data = json.loads(line)
                            print(f"HTMLValidationThread: Parsed JSON: {data}", flush=True)
                            if "result" in data:
                                html_report = data["result"]
                            elif "error" in data:
                                html_report = {"error": data["error"]}
                        except json.JSONDecodeError as e:
                            print(f"HTMLValidationThread: JSON decode error: {str(e)}", flush=True)
            stderr = self.process.stderr.read().strip()
            if stderr and not self.is_canceled:
                print(f"HTMLValidationThread: stderr: {stderr}", flush=True)
                if not html_report:
                    html_report = {"error": f"Subprocess error: {stderr}"}
            return_code = self.process.poll()
            print(f"HTMLValidationThread: Subprocess return code: {return_code}", flush=True)
            if not html_report and not self.is_canceled:
                html_report = {"error": "No valid JSON response received"}
            if not self.is_canceled:
                print(f"HTMLValidationThread: Emitting result: {html_report}", flush=True)
                self.result.emit(html_report)
        except subprocess.TimeoutExpired:
            if self.process:
                self.process.terminate()
                try:
                    self.process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.process.kill()
            html_report = {"error": "Validation timed out"}
            print(f"HTMLValidationThread: Timeout error: {html_report}", flush=True)
            self.result.emit(html_report)
        except Exception as e:
            html_report = {"error": f"Thread exception: {str(e)}"}
            print(f"HTMLValidationThread: Exception: {html_report}", flush=True)
            self.result.emit(html_report)
        finally:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.process.kill()
            print(f"HTMLValidationThread: Subprocess cleaned up", flush=True)

    def cancel(self):
        self.is_canceled = True
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.terminate()
        self.wait()
        print(f"HTMLValidationThread: Canceled", flush=True)

class ValidateOutputWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.pdf_path = None
        self.html_path = None
        self.validation_report = None
        self.button_info_labels = {}
        self.markdown_viewers = []

        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor("#1F252A"))
        self.setPalette(palette)

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(15, 15, 15, 15)
        self.layout.setSpacing(5)
        self.setLayout(self.layout)

        # Button panel will be added at the top (after button creation below)
        
        # Content area (feedback, tables, etc.)
        self.content_layout = QVBoxLayout()
        self.content_layout.setSpacing(5)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.feedback_label = QLabel("Select a check to continue")
        self.feedback_label.setFont(QFont("Helvetica", 12))
        self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
        self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(self.feedback_label, stretch=0)

        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setFont(QFont("Helvetica", 10))
        self.table.setAlternatingRowColors(True)
        self.table.setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.setWordWrap(True)
        self.table.setSortingEnabled(False)
        self.content_layout.addWidget(self.table, stretch=0)

        self.external_table = QTableWidget()
        self.external_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.external_table.setFont(QFont("Helvetica", 10))
        self.external_table.setAlternatingRowColors(True)
        self.external_table.setVisible(False)
        external_header = self.external_table.horizontalHeader()
        external_header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.external_table.verticalHeader().setDefaultSectionSize(30)
        self.external_table.setWordWrap(True)
        self.external_table.setSortingEnabled(False)
        self.content_layout.addWidget(self.external_table, stretch=0)

        button_panel = QHBoxLayout()
        button_panel.setSpacing(8)
        button_panel.setContentsMargins(0, 0, 0, 5)

        pdf_layout = QVBoxLayout()
        pdf_icon_container = QWidget()
        pdf_icon_container.setFixedHeight(40)
        pdf_icon_layout = QHBoxLayout()
        pdf_icon_container.setLayout(pdf_icon_layout)
        pdf_icon_container.setStyleSheet("background-color: transparent;")

        pdf_info_label = QLabel()
        pdf_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio)
            pdf_info_label.setPixmap(pixmap)
        else:
            pixmap = QPixmap(16, 16)
            pixmap.fill(Qt.GlobalColor.transparent)
            pdf_info_label.setPixmap(pixmap)
        pdf_info_label.setStyleSheet("background-color: transparent; border: none;")
        pdf_info_label.setCursor(Qt.CursorShape.PointingHandCursor)
        pdf_info_label.setVisible(False)
        pdf_info_label.mousePressEvent = lambda event: self.open_markdown_help("Validate PDF")
        self.button_info_labels["Validate PDF"] = pdf_info_label
        pdf_icon_layout.addWidget(pdf_info_label)

        self.validate_pdf_btn = QPushButton("Validate PDF")
        self.validate_pdf_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.validate_pdf_btn.setMinimumSize(150, 30)
        self.validate_pdf_btn.setStyleSheet("background-color: #0D6E6E; color: #FFFFFF; padding: 5px 10px; border-radius: 4px; border: 1px solid #0A5555;")
        pdf_layout.addWidget(pdf_icon_container)
        pdf_layout.addWidget(self.validate_pdf_btn)
        button_panel.addLayout(pdf_layout)

        html_layout = QVBoxLayout()
        html_icon_container = QWidget()
        html_icon_container.setFixedHeight(40)
        html_icon_layout = QHBoxLayout()
        html_icon_container.setLayout(html_icon_layout)
        html_icon_container.setStyleSheet("background-color: transparent;")

        html_info_label = QLabel()
        html_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio)
            html_info_label.setPixmap(pixmap)
        else:
            pixmap = QPixmap(16, 16)
            pixmap.fill(Qt.GlobalColor.transparent)
            html_info_label.setPixmap(pixmap)
        html_info_label.setStyleSheet("background-color: transparent; border: none;")
        html_info_label.setCursor(Qt.CursorShape.PointingHandCursor)
        html_info_label.setVisible(False)
        html_info_label.mousePressEvent = lambda event: self.open_markdown_help("Validate HTML")
        self.button_info_labels["Validate HTML"] = html_info_label
        html_icon_layout.addWidget(html_info_label)

        self.validate_html_btn = QPushButton("Validate HTML")
        self.validate_html_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.validate_html_btn.setMinimumSize(150, 30)
        self.validate_html_btn.setStyleSheet("background-color: #0D6E6E; color: #FFFFFF; padding: 5px 10px; border-radius: 4px; border: 1px solid #0A5555;")
        html_layout.addWidget(html_icon_container)
        html_layout.addWidget(self.validate_html_btn)
        button_panel.addLayout(html_layout)

        # Add layouts in correct order: buttons at top, content in middle, back button at bottom
        self.layout.addLayout(button_panel, stretch=0)
        self.layout.addLayout(self.content_layout, stretch=1)

        self.bottom_panel = QHBoxLayout()
        self.bottom_panel.setSpacing(8)
        self.bottom_panel.setContentsMargins(0, 5, 0, 0)
        self.back_btn = QPushButton("Back")
        self.back_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.back_btn.setMinimumSize(150, 30)
        self.back_btn.setStyleSheet("background-color: #0D6E6E; color: #FFFFFF; padding: 5px 10px; border-radius: 4px; border: 1px solid #0A5555;")
        self.bottom_panel.addWidget(self.back_btn)
        self.layout.addLayout(self.bottom_panel, stretch=0)

        self.setStyleSheet("""
            ValidateOutputWidget, QWidget {
                background-color: #1F252A;
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
        self.validate_pdf_btn.clicked.connect(self.validate_pdf)
        self.validate_html_btn.clicked.connect(self.validate_html)
        self.back_btn.clicked.connect(self.cancel_and_return)

        self.table_check_thread = None
        self.link_check_thread = None
        self.html_validation_thread = None

    def open_markdown_help(self, button_name):
        md_name = button_name.lower().replace(" ", "_") + ".md"
        md_path = os.path.join(os.path.dirname(__file__), "docs", md_name)
        if not os.path.exists(md_path):
            return
        viewer = MarkdownViewer(md_path, button_name, self.parent_window)
        viewer.show()
        self.markdown_viewers.append(viewer)

    def update_help_ui(self):
        help_enabled = self.parent_window.help_enabled if self.parent_window else False
        for label in self.button_info_labels.values():
            label.setVisible(help_enabled)

    def clear_content(self):
        for i in reversed(range(self.content_layout.count())):
            item = self.content_layout.itemAt(i)
            if item.widget():
                widget = item.widget()
                self.content_layout.removeWidget(widget)
                widget.setParent(None)
            elif item.layout():
                self.clear_layout(item.layout())

    def clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                widget = item.widget()
                widget.setParent(None)
            elif item.layout():
                self.clear_layout(item.layout())

    def reset_widget(self):
        self.cancel_checks()
        self.clear_content()
        self.pdf_path = None
        self.html_path = None
        self.validation_report = None
        self.feedback_label.setText("Select a check to continue")
        self.feedback_label.setFont(QFont("Helvetica", 12))
        self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
        self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(self.feedback_label, stretch=0)
        self.validate_pdf_btn.setText("Validate PDF")
        self.validate_html_btn.setText("Validate HTML")
        self.validate_pdf_btn.clicked.disconnect()
        self.validate_html_btn.clicked.disconnect()
        self.validate_pdf_btn.clicked.connect(self.validate_pdf)
        self.validate_html_btn.clicked.connect(self.validate_html)
        self.back_btn.clicked.disconnect()
        self.back_btn.clicked.connect(self.cancel_and_return)
        self.validate_pdf_btn.setEnabled(True)
        self.validate_html_btn.setEnabled(True)

    def cancel_checks(self):
        if self.table_check_thread and self.table_check_thread.isRunning():
            self.table_check_thread.cancel()
            self.table_check_thread = None
        if self.link_check_thread and self.link_check_thread.isRunning():
            self.link_check_thread.cancel()
            self.link_check_thread = None
        if self.html_validation_thread and self.html_validation_thread.isRunning():
            self.html_validation_thread.cancel()
            self.html_validation_thread = None
        self.clear_content()
        self.feedback_label.setText("Validation canceled")
        self.feedback_label.setFont(QFont("Helvetica", 12))
        self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
        self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(self.feedback_label, stretch=0)
        self.validate_pdf_btn.setEnabled(True)
        self.validate_html_btn.setEnabled(True)

    def cancel_and_return(self):
        self.cancel_checks()
        if self.link_check_thread:
            self.link_check_thread.wait(2000)
            self.link_check_thread = None
        if self.table_check_thread:
            self.table_check_thread.wait(2000)
            self.table_check_thread = None
        if self.html_validation_thread:
            self.html_validation_thread.wait(2000)
            self.html_validation_thread = None
        self.parent_window.return_to_main_menu()

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
        self.feedback_label.setVisible(True)
        self.feedback_label.setText("Select a PDF file...")
        self.feedback_label.setFont(QFont("Helvetica", 12))
        self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
        self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(self.feedback_label, stretch=0)
        self.validate_pdf_btn.setEnabled(False)
        self.validate_html_btn.setEnabled(False)
        pdf_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select PDF File",
            "",
            "PDF Files (*.pdf);;All Files (*)"
        )
        if not pdf_path:
            self.clear_content()
            self.feedback_label.setText("Select a check to continue")
            self.feedback_label.setFont(QFont("Helvetica", 12))
            self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
            self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.feedback_label.setVisible(True)
            self.content_layout.addWidget(self.feedback_label, stretch=0)
            self.validate_pdf_btn.setEnabled(True)
            self.validate_html_btn.setEnabled(True)
            return
        try:
            if not os.path.exists(pdf_path):
                raise FileNotFoundError("PDF file does not exist")
            file_size_bytes = os.path.getsize(pdf_path)
            file_size_mb = file_size_bytes / (1024 * 1024)
            if file_size_bytes == 0:
                raise ValueError("PDF file is empty")
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
            self.clear_content()
            self.feedback_label.setFont(QFont("Helvetica", 12))
            self.feedback_label.setText("\n".join(metadata_lines))
            self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
            self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.feedback_label.setVisible(True)
            self.content_layout.addWidget(self.feedback_label, stretch=0)
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
            self.clear_content()
            self.feedback_label.setText("Error: Invalid PDF structure")
            self.feedback_label.setFont(QFont("Helvetica", 12))
            self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
            self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.feedback_label.setVisible(True)
            self.content_layout.addWidget(self.feedback_label, stretch=0)
            self.validate_pdf_btn.setText("Validate PDF")
            self.validate_html_btn.setText("Validate HTML")
            self.validate_pdf_btn.clicked.disconnect()
            self.validate_html_btn.clicked.disconnect()
            self.validate_pdf_btn.clicked.connect(self.validate_pdf)
            self.validate_html_btn.clicked.connect(self.validate_html)
            self.back_btn.clicked.disconnect()
            self.back_btn.clicked.connect(self.cancel_and_return)
            self.validate_pdf_btn.setEnabled(True)
            self.validate_html_btn.setEnabled(True)
        except PermissionError:
            self.clear_content()
            self.feedback_label.setText("Error: Permission denied accessing PDF")
            self.feedback_label.setFont(QFont("Helvetica", 12))
            self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
            self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.feedback_label.setVisible(True)
            self.content_layout.addWidget(self.feedback_label, stretch=0)
            self.validate_pdf_btn.setText("Validate PDF")
            self.validate_html_btn.setText("Validate HTML")
            self.validate_pdf_btn.clicked.disconnect()
            self.validate_html_btn.clicked.disconnect()
            self.validate_pdf_btn.clicked.connect(self.validate_pdf)
            self.validate_html_btn.clicked.connect(self.validate_html)
            self.back_btn.clicked.disconnect()
            self.back_btn.clicked.connect(self.cancel_and_return)
            self.validate_pdf_btn.setEnabled(True)
            self.validate_html_btn.setEnabled(True)
        except Exception as e:
            self.clear_content()
            self.feedback_label.setText(f"Error: Failed to validate PDF: {str(e)}")
            self.feedback_label.setFont(QFont("Helvetica", 12))
            self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
            self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.feedback_label.setVisible(True)
            self.content_layout.addWidget(self.feedback_label, stretch=0)
            self.validate_pdf_btn.setText("Validate PDF")
            self.validate_html_btn.setText("Validate HTML")
            self.validate_pdf_btn.clicked.disconnect()
            self.validate_html_btn.clicked.disconnect()
            self.validate_pdf_btn.clicked.connect(self.validate_pdf)
            self.validate_html_btn.clicked.connect(self.validate_html)
            self.back_btn.clicked.disconnect()
            self.back_btn.clicked.connect(self.cancel_and_return)
            self.validate_pdf_btn.setEnabled(True)
            self.validate_html_btn.setEnabled(True)

    def validate_html(self):
        self.clear_content()
        self.feedback_label.setVisible(True)
        self.feedback_label.setText("Select an HTML file...")
        self.feedback_label.setFont(QFont("Helvetica", 12))
        self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
        self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(self.feedback_label, stretch=0)
        self.validate_pdf_btn.setEnabled(False)
        self.validate_html_btn.setEnabled(False)
        self.back_btn.setEnabled(False)
        html_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select HTML File (index.html)",
            "",
            "HTML Files (index.html);;All Files (*)"
        )
        if not html_path:
            self.clear_content()
            self.feedback_label.setText("Select a check to continue")
            self.feedback_label.setFont(QFont("Helvetica", 12))
            self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
            self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.feedback_label.setVisible(True)
            self.content_layout.addWidget(self.feedback_label, stretch=0)
            self.validate_pdf_btn.setEnabled(True)
            self.validate_html_btn.setEnabled(True)
            self.back_btn.setEnabled(True)
            return
        try:
            if not os.path.exists(html_path):
                raise FileNotFoundError("HTML file does not exist")
            file_size_bytes = os.path.getsize(html_path)
            file_size_mb = file_size_bytes / (1024 * 1024)
            if file_size_bytes == 0:
                raise ValueError("HTML file is empty")
            file_name = os.path.basename(html_path)
            self.clear_content()
            self.feedback_label.setFont(QFont("Helvetica", 12))
            self.feedback_label.setText(f"Validating HTML: {file_name}\nSize: {file_size_mb:.2f} MB\nProcessing...")
            self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
            self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.feedback_label.setVisible(True)
            self.content_layout.addWidget(self.feedback_label, stretch=0)
            QApplication.processEvents()
            self.html_path = html_path
            self.html_validation_thread = HTMLValidationThread(self.html_path, "links_and_images")
            self.html_validation_thread.result.connect(self.display_html_report)
            self.html_validation_thread.start()
        except FileNotFoundError:
            self.clear_content()
            self.feedback_label.setText("Error: HTML file does not exist")
            self.feedback_label.setFont(QFont("Helvetica", 12))
            self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
            self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.feedback_label.setVisible(True)
            self.content_layout.addWidget(self.feedback_label, stretch=0)
            self.validate_pdf_btn.setEnabled(True)
            self.validate_html_btn.setEnabled(True)
            self.back_btn.setEnabled(True)
        except ValueError:
            self.clear_content()
            self.feedback_label.setText("Error: HTML file is empty")
            self.feedback_label.setFont(QFont("Helvetica", 12))
            self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
            self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.feedback_label.setVisible(True)
            self.content_layout.addWidget(self.feedback_label, stretch=0)
            self.validate_pdf_btn.setEnabled(True)
            self.validate_html_btn.setEnabled(True)
            self.back_btn.setEnabled(True)
        except Exception as e:
            self.clear_content()
            self.feedback_label.setText(f"Error: Failed to start HTML validation: {str(e)}")
            self.feedback_label.setFont(QFont("Helvetica", 12))
            self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
            self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.feedback_label.setVisible(True)
            self.content_layout.addWidget(self.feedback_label, stretch=0)
            self.validate_pdf_btn.setEnabled(True)
            self.validate_html_btn.setEnabled(True)
            self.back_btn.setEnabled(True)

    def check_tables(self):
        if not self.pdf_path:
            self.clear_content()
            self.feedback_label.setText("Select a check to continue")
            self.feedback_label.setFont(QFont("Helvetica", 12))
            self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
            self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.content_layout.addWidget(self.feedback_label, stretch=0)
            self.validate_pdf_btn.setEnabled(True)
            self.validate_html_btn.setEnabled(True)
            self.back_btn.setEnabled(True)
            return
        self.validate_pdf_btn.setEnabled(False)
        self.validate_html_btn.setEnabled(False)
        self.clear_content()
        self.feedback_label.setFont(QFont("Helvetica", 12))
        self.feedback_label.setText("Table Check: Processing... (Click Back to cancel)")
        self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
        self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.feedback_label.setVisible(True)
        self.content_layout.addWidget(self.feedback_label, stretch=0)
        QApplication.processEvents()
        self.table_check_thread = TableCheckThread(self.pdf_path)
        self.table_check_thread.progress.connect(lambda msg: self.feedback_label.setText(msg))
        self.table_check_thread.result.connect(self.display_table_report)
        self.table_check_thread.start()

    def check_links(self):
        if not self.pdf_path:
            self.clear_content()
            self.feedback_label.setText("Select a check to continue")
            self.feedback_label.setFont(QFont("Helvetica", 12))
            self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
            self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.content_layout.addWidget(self.feedback_label, stretch=0)
            self.validate_pdf_btn.setEnabled(True)
            self.validate_html_btn.setEnabled(True)
            self.back_btn.setEnabled(True)
            return
        self.validate_pdf_btn.setEnabled(False)
        self.validate_html_btn.setEnabled(False)
        self.clear_content()
        self.feedback_label.setFont(QFont("Helvetica", 12))
        self.feedback_label.setText("Link Report: Processing... (Click Back to cancel)")
        self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
        self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.feedback_label.setVisible(True)
        self.content_layout.addWidget(self.feedback_label, stretch=0)
        QApplication.processEvents()
        self.link_check_thread = LinkCheckThread(self.pdf_path)
        self.link_check_thread.progress.connect(lambda msg: self.feedback_label.setText(msg))
        self.link_check_thread.result.connect(self.display_link_report)
        self.link_check_thread.start()

    def display_table_report(self, overflow_pages):
        print(f"display_table_report: Received report: {overflow_pages}", flush=True)
        self.clear_content()
        self.feedback_label.setFont(QFont("Helvetica", 14, QFont.Weight.Bold))
        if not overflow_pages or (isinstance(overflow_pages, list) and len(overflow_pages) == 0):
            self.feedback_label.setText("No overflowing tables detected")
            self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
            self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.feedback_label.setVisible(True)
            self.content_layout.addWidget(self.feedback_label, stretch=0)
        elif isinstance(overflow_pages, list) and overflow_pages and isinstance(overflow_pages[0], str) and overflow_pages[0].startswith("Error"):
            self.feedback_label.setText(f"Table Check: {overflow_pages[0]}")
            self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
            self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.feedback_label.setVisible(True)
            self.content_layout.addWidget(self.feedback_label, stretch=0)
        elif overflow_pages:
            try:
                overflow_pages.sort(key=lambda x: (0, int(x)) if x.isdigit() else (1, x.lower()))
                overflow_text = "Overflowing Table Detected on Pages:\n" + "\n".join(f"--Page {p}" for p in overflow_pages)
            except (ValueError, TypeError):
                overflow_text = "Overflowing Table Detected on Pages:\n" + "\n".join(f"--Page {p}" for p in overflow_pages)
            self.feedback_label.setText(overflow_text)
            self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
            self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.feedback_label.setVisible(True)
            self.content_layout.addWidget(self.feedback_label, stretch=0)
        else:
            self.feedback_label.setText("No Overflowing Tables Detected")
            self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
            self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.feedback_label.setVisible(True)
            self.content_layout.addWidget(self.feedback_label, stretch=0)
        self.validate_pdf_btn.setEnabled(True)
        self.validate_html_btn.setEnabled(True)
        self.back_btn.setEnabled(True)

    def display_link_report(self, link_report):
        print(f"display_link_report: Received report: {link_report}", flush=True)
        self.clear_content()
        self.feedback_label.setFont(QFont("Helvetica", 12))
        if not isinstance(link_report, dict):
            self.feedback_label.setText("Link Report: Invalid response format")
            self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
            self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.feedback_label.setVisible(True)
            self.content_layout.addWidget(self.feedback_label, stretch=0)
        elif "error" in link_report:
            self.feedback_label.setText(f"Link Report: {link_report['error']}")
            self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
            self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.feedback_label.setVisible(True)
            self.content_layout.addWidget(self.feedback_label, stretch=0)
        elif "result" in link_report:
            external = link_report["result"]
            total_external = external.get("total_links", 0)
            redirected_links = external.get("redirected", [])
            invalid_external = external.get("invalid", [])
            unreachable_links = external.get("unreachable", [])
            self.feedback_label.setText(f"Link Report: {total_external} External Links.")
            self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
            self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.feedback_label.setVisible(True)
            self.content_layout.addWidget(self.feedback_label, stretch=0)
            if not (redirected_links or invalid_external or unreachable_links):
                self.feedback_label.setText(self.feedback_label.text() + "\nAll external links are valid.")
            else:
                external_label = QLabel("External Link Validation Results:")
                external_label.setFont(QFont("Helvetica", 12, QFont.Weight.Bold))
                external_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
                self.content_layout.addWidget(external_label, stretch=0)
                self.external_table.setRowCount(len(redirected_links) + len(invalid_external) + len(unreachable_links))
                self.external_table.setColumnCount(4)
                self.external_table.setHorizontalHeaderLabels(["Pages", "Link", "Redirector Link", "Status"])
                external_header = self.external_table.horizontalHeader()
                external_header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
                self.external_table.setWordWrap(True)
                self.external_table.setColumnWidth(3, 200)
                for row, issue in enumerate(redirected_links + invalid_external + unreachable_links):
                    pages_str = ", ".join(f"{p} ({c})" if c > 1 else p for p, c in sorted(issue["pages_counts"].items()))
                    page_item = QTableWidgetItem(pages_str)
                    page_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                    page_item.setToolTip(f"Pages: {pages_str}")
                    self.external_table.setItem(row, 0, page_item)
                    link_item = QTableWidgetItem(issue["url"])
                    link_font = QFont("Helvetica", 12)
                    link_font.setUnderline(True)
                    link_item.setFont(link_font)
                    link_item.setForeground(QColor("#0D6E6E"))
                    link_item.setData(Qt.ItemDataRole.UserRole, issue["url"])
                    link_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                    link_item.setToolTip(f"Click to open: {issue['url']}")
                    self.external_table.setItem(row, 1, link_item)
                    redirector_item = QTableWidgetItem(issue.get("redirected_to", "N/A"))
                    if issue.get("redirected_to"):
                        redirector_font = QFont("Helvetica", 12)
                        redirector_font.setUnderline(True)
                        redirector_item.setFont(redirector_font)
                        redirector_item.setForeground(QColor("#0D6E6E"))
                        redirector_item.setData(Qt.ItemDataRole.UserRole, issue["redirected_to"])
                        redirector_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                        redirector_item.setToolTip(f"Click to open: {issue['redirected_to']}")
                    self.external_table.setItem(row, 2, redirector_item)
                    status_item = QTableWidgetItem(issue["reason"])
                    status_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                    self.external_table.setItem(row, 3, status_item)
                self.external_table.resizeRowsToContents()
                self.external_table.cellClicked.connect(self.open_external_url)
                self.external_table.setVisible(True)
                self.content_layout.addWidget(self.external_table, stretch=0)
        self.validate_pdf_btn.setEnabled(True)
        self.validate_html_btn.setEnabled(True)
        self.back_btn.setEnabled(True)

    def display_html_report(self, html_report):
        print(f"display_html_report: Received report: {html_report}", flush=True)
        self.clear_content()
        self.feedback_label.setFont(QFont("Helvetica", 12))
        
        if not isinstance(html_report, dict):
            self.feedback_label.setText("HTML Validation: Invalid response format")
            self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
            self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.feedback_label.setVisible(True)
            self.content_layout.addWidget(self.feedback_label, stretch=0)
        elif "error" in html_report:
            self.feedback_label.setText(f"HTML Validation: {html_report['error']}")
            self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
            self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.feedback_label.setVisible(True)
            self.content_layout.addWidget(self.feedback_label, stretch=0)
        else:
            total_links = html_report.get("total_internal_links", 0)
            total_images = html_report.get("total_images", 0)
            link_issues = html_report.get("link_issues", [])
            image_issues = html_report.get("image_issues", [])
            external_links = html_report.get("external_links", {})
            total_external = external_links.get("total_external_links", 0)
            
            summary = [
                f"HTML Validation Report:",
                f"Total Internal Links: {total_links}",
                f"Total Images: {total_images}",
                f"Link Issues: {len(link_issues)}",
                f"Image Issues: {len(image_issues)}",
                f"Total External Links: {total_external}"
            ]
            self.feedback_label.setText("\n".join(summary))
            self.feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
            self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.feedback_label.setVisible(True)
            self.content_layout.addWidget(self.feedback_label, stretch=0)
            
            if not (link_issues or image_issues or external_links.get("redirected") or external_links.get("invalid") or external_links.get("unreachable")):
                self.feedback_label.setText(self.feedback_label.text() + "\nNo issues detected.")
            else:
                if link_issues or image_issues:
                    internal_label = QLabel("Internal Link and Image Issues:")
                    internal_label.setFont(QFont("Helvetica", 12, QFont.Weight.Bold))
                    internal_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
                    self.content_layout.addWidget(internal_label, stretch=0)
                    
                    self.table.setRowCount(len(link_issues) + len(image_issues))
                    self.table.setColumnCount(4)
                    self.table.setHorizontalHeaderLabels(["File", "Link/Image", "Location", "Issue"])
                    header = self.table.horizontalHeader()
                    header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
                    self.table.setWordWrap(True)
                    
                    row = 0
                    for issue in link_issues:
                        file_item = QTableWidgetItem(issue["file"])
                        file_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                        file_item.setToolTip(f"Click to open: {issue['file']}")
                        file_item.setData(Qt.ItemDataRole.UserRole, os.path.join(os.path.dirname(self.html_path), issue["location"]))
                        file_font = QFont("Helvetica", 12)
                        file_font.setUnderline(True)
                        file_item.setFont(file_font)
                        file_item.setForeground(QColor("#0D6E6E"))
                        self.table.setItem(row, 0, file_item)
                        
                        href_item = QTableWidgetItem(issue["href"])
                        href_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                        self.table.setItem(row, 1, href_item)
                        
                        location_item = QTableWidgetItem(issue["location"])
                        location_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                        location_item.setToolTip(f"Location: {issue['location']}")
                        self.table.setItem(row, 2, location_item)
                        
                        issue_item = QTableWidgetItem(issue["issue"])
                        issue_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                        self.table.setItem(row, 3, issue_item)
                        row += 1
                        
                    for issue in image_issues:
                        file_item = QTableWidgetItem(issue["file"])
                        file_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                        file_item.setToolTip(f"Click to open: {issue['file']}")
                        file_item.setData(Qt.ItemDataRole.UserRole, os.path.join(os.path.dirname(self.html_path), issue["location"]))
                        file_font = QFont("Helvetica", 12)
                        file_font.setUnderline(True)
                        file_item.setFont(file_font)
                        file_item.setForeground(QColor("#0D6E6E"))
                        self.table.setItem(row, 0, file_item)
                        
                        src_item = QTableWidgetItem(issue["src"])
                        src_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                        self.table.setItem(row, 1, src_item)
                        
                        location_item = QTableWidgetItem(issue["location"])
                        location_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                        location_item.setToolTip(f"Location: {issue['location']}")
                        self.table.setItem(row, 2, location_item)
                        
                        issue_item = QTableWidgetItem(issue["issue"])
                        issue_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                        self.table.setItem(row, 3, issue_item)
                        row += 1
                        
                    self.table.resizeRowsToContents()
                    self.table.cellClicked.connect(self.open_internal_url)
                    self.table.setVisible(True)
                    self.content_layout.addWidget(self.table, stretch=0)
                
                if external_links.get("redirected") or external_links.get("invalid") or external_links.get("unreachable"):
                    external_label = QLabel("External Link Issues:")
                    external_label.setFont(QFont("Helvetica", 12, QFont.Weight.Bold))
                    external_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
                    self.content_layout.addWidget(external_label, stretch=0)
                    
                    external_issues = (
                        external_links.get("redirected", []) +
                        external_links.get("invalid", []) +
                        external_links.get("unreachable", [])
                    )
                    self.external_table.setRowCount(len(external_issues))
                    self.external_table.setColumnCount(4)
                    self.external_table.setHorizontalHeaderLabels(["Files", "Link", "Redirector Link", "Status"])
                    external_header = self.external_table.horizontalHeader()
                    external_header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
                    self.external_table.setWordWrap(True)
                    self.external_table.setColumnWidth(3, 200)
                    
                    for row, issue in enumerate(external_issues):
                        files_str = ", ".join(issue["files"])
                        file_item = QTableWidgetItem(files_str)
                        file_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                        file_item.setToolTip(f"Click to open first file: {issue['files'][0]}")
                        file_item.setData(Qt.ItemDataRole.UserRole, os.path.join(os.path.dirname(self.html_path), issue["files"][0]))
                        file_font = QFont("Helvetica", 12)
                        file_font.setUnderline(True)
                        file_item.setFont(file_font)
                        file_item.setForeground(QColor("#0D6E6E"))
                        self.external_table.setItem(row, 0, file_item)
                        
                        link_item = QTableWidgetItem(issue["url"])
                        link_font = QFont("Helvetica", 12)
                        link_font.setUnderline(True)
                        link_item.setFont(link_font)
                        link_item.setForeground(QColor("#0D6E6E"))
                        link_item.setData(Qt.ItemDataRole.UserRole, issue["url"])
                        link_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                        link_item.setToolTip(f"Click to open: {issue['url']}")
                        self.external_table.setItem(row, 1, link_item)
                        
                        redirector_item = QTableWidgetItem(issue.get("redirected_to", "N/A"))
                        if issue.get("redirected_to"):
                            redirector_font = QFont("Helvetica", 12)
                            redirector_font.setUnderline(True)
                            redirector_item.setFont(redirector_font)
                            redirector_item.setForeground(QColor("#0D6E6E"))
                            redirector_item.setData(Qt.ItemDataRole.UserRole, issue["redirected_to"])
                            redirector_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                            redirector_item.setToolTip(f"Click to open: {issue['redirected_to']}")
                        self.external_table.setItem(row, 2, redirector_item)
                        
                        status_item = QTableWidgetItem(issue["reason"])
                        status_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                        self.external_table.setItem(row, 3, status_item)
                        
                    self.external_table.resizeRowsToContents()
                    self.external_table.cellClicked.connect(self.open_external_url)
                    self.external_table.setVisible(True)
                    self.content_layout.addWidget(self.external_table, stretch=0)
            
        self.validate_pdf_btn.setEnabled(True)
        self.validate_html_btn.setEnabled(True)
        self.back_btn.setEnabled(True)

    def open_internal_url(self, row, col):
        if col not in [0, 1]:  # Only "File" (col=0) and "Link/Image" (col=1) are clickable
            return
        item = self.table.item(row, col)
        if item:
            user_role_data = item.data(Qt.ItemDataRole.UserRole)
            if user_role_data:
                url = QUrl.fromLocalFile(user_role_data) if col == 0 else QUrl(user_role_data)
                if url.isValid():
                    QDesktopServices.openUrl(url)

    def open_external_url(self, row, col):
        if col not in [0, 1, 2]:  # Only "Files" (col=0), "Link" (col=1), and "Redirector Link" (col=2) are clickable
            return
        item = self.external_table.item(row, col)
        if item:
            user_role_data = item.data(Qt.ItemDataRole.UserRole)
            if user_role_data:
                url = QUrl.fromLocalFile(user_role_data) if col == 0 else QUrl(user_role_data)
                if url.isValid():
                    QDesktopServices.openUrl(url)