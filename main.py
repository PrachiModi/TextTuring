import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QStackedWidget, QFileDialog, QGridLayout, QSizePolicy
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QFont, QPixmap, QColor, QPainter, QPalette
from check_image_sanity import CheckImageSanityWidget
from file_sanity import FileSanityWidget
from validate_output import ValidateOutputWidget
from validate_xmls import ValidateXMLsWidget
import os
import shutil
import time
import tempfile
from markdown_viewer import MarkdownViewer  # Import Markdown viewer


class CustomToggle(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(40, 20)
        self.setStyleSheet("""
            QPushButton {
                background-color: #d3d3d3;
                border-radius: 10px;
                padding: 1px;
            }
            QPushButton:checked {
                background-color: #0D6E6E;
            }
        """)
        self.setChecked(False)
        self.update_toggle()


    def update_toggle(self):
        if self.isChecked():
            self.setStyleSheet(self.styleSheet() + """
                QPushButton:checked {
                    background-color: #0D6E6E;
                }
            """)
        else:
            self.setStyleSheet(self.styleSheet() + """
                QPushButton {
                    background-color: #d3d3d3;
                }
            """)


    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        diameter = 18
        x_pos = 20 if self.isChecked() else 1
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(x_pos, 1, diameter, diameter)


    def mousePressEvent(self, event):
        self.toggle()
        self.update_toggle()


    def toggle(self):
        self.setChecked(not self.isChecked())


class TextTuringApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TextTuring")
        self.setGeometry(100, 100, 800, 600)
        self.help_enabled = False
        self.markdown_viewers = []  # Track open Markdown viewers
        self.button_info_labels = {}  # Map button names to info labels


        # Set application-wide dark background
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#1F252A"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#1F252A"))
        self.setPalette(palette)
        self.setStyleSheet("QMainWindow, QWidget { background-color: #1F252A; }")


        # Main widget
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        main_widget.setLayout(main_layout)


        # Header with custom toggle slider
        header_widget = QWidget()
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_widget.setLayout(header_layout)


        self.toggle_widget = QWidget()
        toggle_layout = QHBoxLayout()
        toggle_layout.setContentsMargins(0, 0, 0, 0)
        self.toggle_widget.setLayout(toggle_layout)


        self.toggle_label = QLabel("Enable Help")
        self.toggle_label.setFont(QFont("Helvetica", 10))
        self.toggle_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
        toggle_layout.addWidget(self.toggle_label)


        self.toggle_switch = CustomToggle()
        self.toggle_switch.toggled.connect(self.set_help_enabled)
        toggle_layout.addWidget(self.toggle_switch)


        header_layout.addStretch()
        header_layout.addWidget(self.toggle_widget)


        main_layout.addWidget(header_widget)


        # Stacked widget to manage views
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)


        # Main menu widget
        main_menu_widget = QWidget()
        main_menu_layout = QVBoxLayout()
        main_menu_layout.setContentsMargins(0, 0, 0, 0)
        main_menu_widget.setLayout(main_menu_layout)


        # Image display
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_path = os.path.join(os.path.dirname(__file__), "logo.png")
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            scaled_pixmap = pixmap.scaled(300, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.image_label.setPixmap(scaled_pixmap)
        else:
            print(f"Warning: Image file not found at {image_path}")
        main_menu_layout.addWidget(self.image_label, stretch=1)


        # Button panel
        button_panel = QWidget()
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        button_panel.setLayout(button_layout)


        button_names = ["Back Up", "Directory Cleanup", "Validate XMLs", "Check Image Sanity", "Validate Output", "Exit"]
        self.buttons = []
        for name in button_names:
            btn = QPushButton(name)
            btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
            btn.setStyleSheet("""
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
            """)
            button_layout.addWidget(btn)
            self.buttons.append(btn)


        main_menu_layout.addWidget(button_panel)
        self.stacked_widget.addWidget(main_menu_widget)


        # Add view widgets
        self.file_sanity_widget = FileSanityWidget(self)
        self.validate_xmls_widget = ValidateXMLsWidget(self)
        self.check_image_sanity_widget = CheckImageSanityWidget(self)
        self.validate_output_widget = ValidateOutputWidget(self)
        self.backup_widget = QWidget()
        self.setup_backup_widget()
        self.stacked_widget.addWidget(self.backup_widget)
        self.stacked_widget.addWidget(self.file_sanity_widget)
        self.stacked_widget.addWidget(self.validate_xmls_widget)
        self.stacked_widget.addWidget(self.check_image_sanity_widget)
        self.stacked_widget.addWidget(self.validate_output_widget)


        # Connect buttons
        self.buttons[0].clicked.connect(lambda: self.switch_view(1))  # Backup
        self.buttons[1].clicked.connect(lambda: self.switch_view(2))  # Directory Cleanup
        self.buttons[2].clicked.connect(lambda: self.switch_view(3))  # Validate XMLs
        self.buttons[3].clicked.connect(lambda: self.switch_view(4))  # Check Image Sanity
        self.buttons[4].clicked.connect(lambda: self.switch_view(5))  # Validate Output
        self.buttons[5].clicked.connect(QApplication.quit)  # Exit


    def open_markdown_help(self, button_name):
        """Open the corresponding .md file for the button."""
        md_name = button_name.lower().replace(" ", "_") + ".md"
        md_path = os.path.join(os.path.dirname(__file__), "docs", md_name)
        if not os.path.exists(md_path):
            print(f"Warning: Markdown file not found at {md_path}")
            return
        viewer = MarkdownViewer(md_path, button_name, self)  # Pass self as main_window
        self.markdown_viewers.append(viewer)
        viewer.show()


    def setup_backup_widget(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        self.backup_widget.setLayout(layout)


        self.backup_feedback_label = QLabel("Select a directory to back up")
        self.backup_feedback_label.setFont(QFont("Helvetica", 12))
        self.backup_feedback_label.setStyleSheet("color: #FFFFFF; background-color: transparent;")
        self.backup_feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.backup_feedback_label, stretch=1)


        button_panel = QGridLayout()
        button_panel.setSpacing(8)
        button_panel.setContentsMargins(0, 0, 0, 0)


        # Top row: Icon and Empty cell
        backup_icon_label = QLabel()
        backup_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        backup_icon_label.setFixedSize(16, 16)  # Fixed size to match icon
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio)
            backup_icon_label.setPixmap(pixmap)
        else:
            print(f"Warning: Icon file not found at {icon_path}")
            pixmap = QPixmap(16, 16)
            pixmap.fill(Qt.GlobalColor.transparent)
            backup_icon_label.setPixmap(pixmap)
        backup_icon_label.setCursor(Qt.CursorShape.PointingHandCursor)
        backup_icon_label.setVisible(False)  # Hidden by default
        backup_icon_label.mousePressEvent = lambda event: self.open_markdown_help("Select Directory")
        self.button_info_labels["Select Directory"] = backup_icon_label
        button_panel.addWidget(backup_icon_label, 0, 0, alignment=Qt.AlignmentFlag.AlignCenter)


        empty_label = QLabel()
        empty_label.setFixedSize(16, 16)  # Match icon size for symmetry
        empty_label.setStyleSheet("background-color: transparent;")
        button_panel.addWidget(empty_label, 0, 1, alignment=Qt.AlignmentFlag.AlignCenter)


        # Bottom row: Buttons
        self.backup_btn = QPushButton("Select Directory")
        self.backup_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.backup_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)  # Expand horizontally
        self.backup_btn.setStyleSheet("""
            QPushButton {
                background-color: #0D6E6E;
                color: #FFFFFF;
                padding: 5px 70px;  /* Further increased horizontal padding */
                border-radius: 4px;
                border: 1px solid #0A5555;  /* Removed box-shadow */
            }
            QPushButton:hover {
                background-color: #139999;
                border: 1px solid #0C7A7A;
            }
        """)
        button_panel.addWidget(self.backup_btn, 1, 0, 1, 1, alignment=Qt.AlignmentFlag.AlignCenter)  # Span full column


        self.back_btn = QPushButton("Back")
        self.back_btn.setFont(QFont("Helvetica", 12, QFont.Weight.Medium))
        self.back_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)  # Expand horizontally
        self.back_btn.setStyleSheet("""
            QPushButton {
                background-color: #0D6E6E;
                color: #FFFFFF;
                padding: 5px 70px;  /* Further increased horizontal padding */
                border-radius: 4px;
                border: 1px solid #0A5555;  /* Removed box-shadow */
            }
            QPushButton:hover {
                background-color: #139999;
                border: 1px solid #0C7A7A;
            }
        """)
        button_panel.addWidget(self.back_btn, 1, 1, 1, 1, alignment=Qt.AlignmentFlag.AlignCenter)  # Span full column


        # Set column stretch to maximize button horizontal space across the window
        button_panel.setColumnStretch(0, 50)  # Increased stretch for button column
        button_panel.setColumnStretch(1, 50)  # Increased stretch for button column


        layout.addLayout(button_panel)


        self.backup_btn.clicked.connect(self.create_backup)
        self.back_btn.clicked.connect(self.return_to_main_menu)


    def create_backup(self):
        directory_path = QFileDialog.getExistingDirectory(self, "Select Directory", "")
        if not directory_path:
            self.backup_feedback_label.setText("No directory selected")
            return
        try:
            legacy_dir = os.path.join(directory_path, "LegacyTextTuring")
            os.makedirs(legacy_dir, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            zip_name = f"backup_{timestamp}.zip"
            zip_path = os.path.join(legacy_dir, zip_name)


            # Create a temporary directory
            with tempfile.TemporaryDirectory() as temp_dir:
                # Copy directory contents to temp_dir, excluding LegacyTextTuring
                for item in os.listdir(directory_path):
                    if item == "LegacyTextTuring":
                        continue
                    src = os.path.join(directory_path, item)
                    dst = os.path.join(temp_dir, item)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
                # Create ZIP from temp_dir
                shutil.make_archive(
                    zip_path.replace(".zip", ""),
                    "zip",
                    temp_dir
                )
            self.backup_feedback_label.setText(f"Backup created and stored in LegacyTextTuring/{zip_name}")
        except Exception as e:
            self.backup_feedback_label.setText(f"Error creating backup: {str(e)}")


    def switch_view(self, index):
        """Switch to the specified view in the stacked widget, preserving toggle state."""
        self.stacked_widget.setCurrentIndex(index)
        if hasattr(self, 'toggle_switch') and hasattr(self, 'help_enabled'):
            self.toggle_switch.setChecked(self.help_enabled)
            self.update_help_ui()
        # Reset widget state when switching to Validate Output
        if index == 5 and hasattr(self, 'validate_output_widget') and hasattr(self.validate_output_widget, 'reset_widget'):
            self.validate_output_widget.reset_widget()


    def return_to_main_menu(self):
        """Return to the main menu view, preserving toggle state."""
        self.stacked_widget.setCurrentIndex(0)
        if hasattr(self, 'toggle_switch') and hasattr(self, 'help_enabled'):
            self.toggle_switch.setChecked(self.help_enabled)
            self.update_help_ui()


    def set_help_enabled(self, enabled):
        self.help_enabled = enabled
        if hasattr(self, 'toggle_switch'):
            self.toggle_switch.setChecked(enabled)
        self.update_help_ui()


    def update_help_ui(self):
        """Show/hide info icons based on help_enabled state and update child widgets."""
        for label in self.button_info_labels.values():
            label.setVisible(self.help_enabled)


        for i in range(self.stacked_widget.count()):
            widget = self.stacked_widget.widget(i)
            if hasattr(widget, 'update_help_ui'):
                widget.update_help_ui()


    def closeEvent(self, event):
        """Close all MarkdownViewer instances when the main window closes."""
        for viewer in self.markdown_viewers:
            viewer.close()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = TextTuringApp()
    window.show()
    sys.exit(app.exec())

