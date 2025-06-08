import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QStackedWidget
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPixmap
from check_image_sanity import CheckImageSanityWidget  # Updated to widget
from file_sanity import FileSanityWidget
from validate_output import ValidateOutputWidget  # Updated to widget
from validate_xmls import ValidateXMLsWidget
import os

class TextTuringApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TextTuring")
        self.setGeometry(100, 100, 800, 600)  # Adjusted for larger content

        # Main widget
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        main_widget.setLayout(main_layout)

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

        button_names = ["Directory Cleanup", "Validate XMLs", "Check Image Sanity", "Validate Output", "Exit"]
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
        self.stacked_widget.addWidget(self.file_sanity_widget)
        self.stacked_widget.addWidget(self.validate_xmls_widget)
        self.stacked_widget.addWidget(self.check_image_sanity_widget)
        self.stacked_widget.addWidget(self.validate_output_widget)

        # Connect buttons
        self.buttons[0].clicked.connect(lambda: self.switch_view(1))  # Directory Cleanup
        self.buttons[1].clicked.connect(lambda: self.switch_view(2))  # Validate XMLs
        self.buttons[2].clicked.connect(lambda: self.switch_view(3))  # Check Image Sanity
        self.buttons[3].clicked.connect(lambda: self.switch_view(4))  # Validate Output
        self.buttons[4].clicked.connect(QApplication.quit)  # Exit

        # Apply styling
        self.setStyleSheet("background-color: #1F252A;")

    def switch_view(self, index):
        """Switch to the specified view in the stacked widget."""
        self.stacked_widget.setCurrentIndex(index)

    def return_to_main_menu(self):
        """Return to the main menu view."""
        self.stacked_widget.setCurrentIndex(0)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TextTuringApp()
    window.show()
    sys.exit(app.exec())