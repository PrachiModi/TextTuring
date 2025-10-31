# TextTuring

A comprehensive PyQt6 application for managing, validating, and processing technical documentation (DITA/XML) with graphics, tables, and PDF output validation.

## 🚀 Features

- **Directory Cleanup**: Find and manage unreferenced graphics, XMLs, and unnecessary folders
- **XML Validation**: Validate table widths, graphics references, and structure
- **Image Sanity Checks**: Convert non-PNG images, validate sizes, and optimize graphics
- **Output Validation**: Validate PDF links and HTML content
- **Performance Optimized**: Multiprocessing support for faster processing of large projects
- **Network Drive Detection**: Warns users about slow network folders (Google Drive, OneDrive, etc.)

## 📋 Requirements

### Python
- **Python 3.8+** (tested with Python 3.13)

### Dependencies
See `requirements.txt` for full list:
- PyQt6 (GUI framework)
- Pillow (image processing)
- lxml (XML parsing)
- PyMuPDF (PDF processing)
- pdfplumber (PDF text extraction)
- requests/httpx (HTTP link validation)
- markdown (documentation rendering)

### Optional
- **oxipng**: For PNG optimization (optional, gracefully handled if missing)
  - **macOS**: `brew install oxipng`
  - **Windows**: Download from [oxipng releases](https://github.com/shssoichiro/oxipng/releases) or use `choco install oxipng`
  - **Linux**: `apt-get install oxipng` or `yum install oxipng`

## 🛠️ Installation

### For macOS (Intel & Apple Silicon)

1. **Clone or download the repository**
   ```bash
   cd Project_TextTuring_copy_2
   ```

2. **Create a virtual environment** (recommended)
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application**
   ```bash
   python main.py
   ```

### For Windows

1. **Clone or download the repository**
   ```bash
   cd Project_TextTuring_copy_2
   ```

2. **Create a virtual environment** (recommended)
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application**
   ```bash
   python main.py
   ```

## 📁 Project Structure

```
Project_TextTuring_copy_2/
├── main.py                    # Main application entry point
├── requirements.txt           # Python dependencies
├── docs/                      # Help documentation (markdown)
├── check_image_sanity.py     # Image validation and conversion
├── file_sanity.py             # Directory cleanup utilities
├── validate_xmls.py          # XML/table/graphics validation
├── validate_output.py         # PDF/HTML output validation
├── network_utils.py           # Network drive detection
├── fix_graphics.py            # Graphics validation (multiprocessing)
├── fix_tables.py              # Table validation (multiprocessing)
├── image_report.py            # Image scanning and reporting
├── validate_external_pdf_links.py  # PDF link checker (optimized)
└── [other utility modules]
```

## 🎯 Usage

1. **Launch the application**: Run `python main.py`
2. **Select a feature** from the main menu:
   - **Back Up**: Create ZIP backups of directories
   - **Directory Cleanup**: Find unreferenced files and folders
   - **Validate XMLs**: Check table widths and graphics
   - **Check Image Sanity**: Convert and optimize images
   - **Validate Output**: Check PDF links and HTML content
3. **Enable Help**: Toggle the "Enable Help" switch for contextual help icons

### Performance Tips

- **Local folders are faster**: The app detects network drives and warns you. For best performance, copy your project to a local folder before processing.
- **Large PDFs**: The PDF link checker is optimized for large files (5000+ pages) with adaptive worker scaling.
- **Multiprocessing**: All major validation features use multiprocessing automatically for faster processing.

## 🐛 Troubleshooting

### Windows Issues

- **PyQt6 installation**: If you encounter errors, try upgrading pip first: `python -m pip install --upgrade pip`
- **oxipng not found**: This is optional. The app will work without it, just without PNG optimization.
- **Network paths**: UNC paths (\\server\share) are automatically detected as network drives.

### macOS Issues

- **Permission errors**: Make sure you have read/write permissions for the directories you're processing.
- **Apple Silicon**: The app works natively on both Intel and Apple Silicon Macs.

### General Issues

- **Import errors**: Make sure your virtual environment is activated and all dependencies are installed.
- **Slow performance**: Check if you're processing files on a network drive. Copy to local drive for best performance.

## 🔧 Development

### Running Tests
```bash
# Ensure virtual environment is activated
python main.py
```

### Building Executables

#### macOS (Universal Binary)
```bash
# Install PyInstaller
pip install pyinstaller

# Build universal DMG
pyinstaller --onedir --windowed --name TextTuring main.py
# Then create DMG with create-dmg or similar tool
```

#### Windows
```bash
# Install PyInstaller
pip install pyinstaller

# Build executable
pyinstaller --onedir --windowed --name TextTuring main.py
```

## 📝 Notes

- The app automatically creates `LegacyTextTuring` folders for backups and moved files.
- All validation results are logged to console and displayed in the UI.
- Network drive detection works on Windows, macOS, and Linux.

## 🤝 Contributing

This is a private project. For issues or suggestions, please contact the project maintainer.

## 📄 License

Private project - All rights reserved.

---

**Version**: 1.0  
**Last Updated**: 2024  
**Python Version**: 3.8+  
**Tested Platforms**: macOS (Intel & Apple Silicon), Windows 10/11

