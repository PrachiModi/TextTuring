import sys
import json
import pdfplumber
import fitz  # PyMuPDF for page label extraction

def check_table_overflow(pdf_path):
    """Check for table overflows in the PDF and return a list of page labels."""
    overflow_page_labels = []
    try:
        # Open the PDF with PyMuPDF to access page labels
        doc = fitz.open(pdf_path)
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            for page_num in range(total_pages):
                print(json.dumps({"progress": f"Checking tables: Page {page_num + 1}/{total_pages}"}))
                sys.stdout.flush()
                page = pdf.pages[page_num]
                # Get the page label using PyMuPDF
                fitz_page = doc[page_num]
                page_label = fitz_page.get_label() or str(page_num + 1)  # Fallback to physical page number if label not defined
                tables = page.find_tables(table_settings={
                    "vertical_strategy": "lines_strict",
                    "horizontal_strategy": "lines_strict",
                    "snap_tolerance": 3,
                    "join_tolerance": 3,
                })
                if not tables:
                    tables = page.find_tables(table_settings={
                        "vertical_strategy": "lines",
                        "horizontal_strategy": "lines",
                        "snap_tolerance": 5,
                        "join_tolerance": 5,
                    })
                if not tables:
                    continue

                for table_idx, table in enumerate(tables):
                    try:
                        table_data = table.extract()
                        if not table_data:
                            continue

                        words = page.extract_words()
                        if not words:
                            chars = page.chars
                            words = []
                            current_word = []
                            for char in chars:
                                if not current_word:
                                    current_word.append(char)
                                elif (abs(char["x0"] - current_word[-1]["x1"]) < 2 and
                                      abs(char["top"] - current_word[-1]["top"]) < 2):
                                    current_word.append(char)
                                else:
                                    text = "".join(c["text"] for c in current_word)
                                    x0 = min(c["x0"] for c in current_word)
                                    top = min(c["top"] for c in current_word)
                                    x1 = max(c["x1"] for c in current_word)
                                    bottom = max(c["bottom"] for c in current_word)
                                    words.append({
                                        "text": text,
                                        "x0": x0,
                                        "top": top,
                                        "x1": x1,
                                        "bottom": bottom
                                    })
                                    current_word = [char]
                            if current_word:
                                text = "".join(c["text"] for c in current_word)
                                x0 = min(c["x0"] for c in current_word)
                                top = min(c["top"] for c in current_word)
                                x1 = max(c["x1"] for c in current_word)
                                bottom = max(c["bottom"] for c in current_word)
                                words.append({
                                    "text": text,
                                    "x0": x0,
                                    "top": top,
                                    "x1": x1,
                                    "bottom": bottom
                                })

                        for row_idx, row in enumerate(table_data):
                            for col_idx, cell in enumerate(row):
                                if not cell:
                                    continue

                                cell_info = table.cells[row_idx * len(row) + col_idx]
                                if hasattr(cell_info, "bbox"):
                                    cell_bbox = cell_info.bbox
                                elif isinstance(cell_info, tuple) and len(cell_info) == 4:
                                    cell_bbox = cell_info
                                else:
                                    continue

                                cell_x0, cell_top, cell_x1, cell_bottom = cell_bbox

                                cell_words = []
                                for word in words:
                                    word_x0 = word["x0"]
                                    word_top = word["top"]
                                    word_x1 = word["x1"]
                                    word_bottom = word["bottom"]

                                    if not (word_x1 < cell_x0 or word_x0 > cell_x1 or
                                            word_bottom < cell_top or word_top > cell_bottom):
                                        cell_words.append(word)

                                for word in cell_words:
                                    word_x0 = word["x0"]
                                    word_top = word["top"]
                                    word_x1 = word["x1"]
                                    word_bottom = word["bottom"]

                                    overflow = False
                                    tolerance = 0.5
                                    if word_x0 < cell_x0 - tolerance:
                                        overflow = True
                                    if word_x1 > cell_x1 + tolerance:
                                        overflow = True
                                    if word_top < cell_top - tolerance:
                                        overflow = True
                                    if word_bottom > cell_bottom + tolerance:
                                        overflow = True

                                    if overflow:
                                        if page_label not in overflow_page_labels:
                                            overflow_page_labels.append(page_label)
                                        break  # Stop checking this table once overflow is found

                    except Exception as e:
                        continue  # Continue with the next table

        doc.close()

    except Exception as e:
        print(f"Error checking tables: {str(e)}", file=sys.stderr)
        return []

    return overflow_page_labels

def main(pdf_path):
    """Main function to check table overflows in a PDF."""
    overflow_page_labels = check_table_overflow(pdf_path)
    print(json.dumps({"result": overflow_page_labels}))
    sys.stdout.flush()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python verify_pdf_tables.py <pdf_path>", file=sys.stderr)
        sys.exit(1)
    pdf_path = sys.argv[1]
    main(pdf_path)