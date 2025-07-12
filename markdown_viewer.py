from PyQt6.QtWidgets import QMainWindow, QTextEdit, QVBoxLayout, QWidget
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QRect, Qt as QtEnum, QUrl
import markdown
import os
import logging
import re
from urllib.parse import quote

# Setup basic logging for debugging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

class MarkdownViewer(QMainWindow):
    def __init__(self, md_path, title, main_window):
        super().__init__(main_window)  # Set main_window as parent
        self.setWindowTitle(f"Help: {title}")
        self.main_window = main_window

        # Close any existing MarkdownViewer instance
        if hasattr(main_window, 'markdown_viewer') and main_window.markdown_viewer is not None:
            main_window.markdown_viewer.close()
            main_window.markdown_viewer = None

        # Store this instance in main_window
        main_window.markdown_viewer = self

        # Get main window geometry and calculate offset position
        main_geom = main_window.geometry()
        new_x = main_geom.x() + main_geom.width() + 50
        new_y = main_geom.y()
        screen_geom = main_window.screen().availableGeometry()
        if new_x + 600 > screen_geom.right():
            new_x = main_geom.x() - 600 - 50
        if new_x < screen_geom.left():
            new_x = screen_geom.left()
        self.setGeometry(new_x, new_y, 600, 400)

        # Prevent window from staying on top
        self.setWindowFlags(self.windowFlags() & ~QtEnum.WindowType.WindowStaysOnTopHint)

        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        main_widget.setLayout(layout)

        # Text edit for Markdown content
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Helvetica", 12))
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #FFFFFF;
                color: #000000;
                border-radius: 4px;
                padding: 5px;
            }
        """)
        layout.addWidget(self.text_edit)

        # Load and render Markdown
        self.load_markdown(md_path)

    def load_markdown(self, md_path):
        """Load and render the Markdown file as HTML."""
        try:
            with open(md_path, 'r', encoding='utf-8') as f:
                md_content = f.read()
            # Get the directory of the Markdown file
            base_dir = os.path.dirname(os.path.abspath(md_path))
            logging.debug(f"Markdown file directory: {base_dir}")
            
            # Verify image existence
            image_path = os.path.join(base_dir, "image.png")
            logging.debug(f"Looking for image at: {image_path}")
            if not os.path.exists(image_path):
                logging.error(f"Image file not found: {image_path}")
                self.text_edit.setText(f"Error: Image file not found at {image_path}")
                return

            # Convert Markdown to HTML
            
            html_content = markdown.markdown(md_content, extensions=['extra'])
       
            # Replace relative image paths with encoded file:// URLs and set size
            html_content = re.sub(
                r'<img[^>]+src=["\']([^"\']+)["\']',
                lambda m: f'<img src="file:///{quote(os.path.join(base_dir, m.group(1)).replace(os.sep, "/"))}" width="384" height="384" alt="{m.group(1)}"',
                html_content
            )
            # Wrap HTML content for proper rendering
            html_with_base = f"""
            <html>
            <body>
                {html_content}
            </body>
            </html>
            """
            logging.debug(f"Generated HTML: {html_with_base}")
            self.text_edit.setHtml(html_with_base)
            logging.debug("HTML content set successfully")
        except Exception as e:
            logging.error(f"Error loading Markdown: {str(e)}")
            self.text_edit.setText(f"Error loading help file: {str(e)}")

    def closeEvent(self, event):
        """Ensure proper cleanup when closing."""
        # Clear the reference in main_window
        if hasattr(self.main_window, 'markdown_viewer') and self.main_window.markdown_viewer == self:
            self.main_window.markdown_viewer = None
        event.accept()