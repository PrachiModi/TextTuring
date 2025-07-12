import sys
import json
import pdfplumber
import fitz
from multiprocessing import Pool
import logging

# Configure logging to file for critical errors only
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s',
    handlers=[logging.FileHandler("table_detection.log")]
)

def build_words_from_chars(chars):
    """Build words from characters when extract_words fails."""
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
                "bottom": bottom,
                "fontname": current_word[0]["fontname"] if current_word else None
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
            "bottom": bottom,
            "fontname": current_word[0]["fontname"] if current_word else None
        })
    return words

def process_page(args):
    """Process a single page for table overflows."""
    pdf_path, page_num, total_pages = args
    overflow_page_labels = []
    try:
        doc = fitz.open(pdf_path)
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[page_num]
            page_label = doc[page_num].get_label() or str(page_num + 1)

            if not page.chars and not page.lines:
                return []

            table_settings_strict = {
                "vertical_strategy": "lines_strict",
                "horizontal_strategy": "lines_strict",
                "snap_tolerance": 3,
                "join_tolerance": 3,
            }
            table_settings_loose = {
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
                "snap_tolerance": 5,
                "join_tolerance": 5,
            }

            tables = page.find_tables(table_settings=table_settings_strict)
            if not tables:
                tables = page.find_tables(table_settings=table_settings_loose)
            if not tables:
                return []

            words = page.extract_words(extra_attrs=["fontname"]) or build_words_from_chars(page.chars)

            for table_idx, table in enumerate(tables):
                try:
                    table_data = table.extract()
                    if not table_data:
                        continue

                    for row_idx, row in enumerate(table_data):
                        for col_idx, cell in enumerate(row):
                            if not cell:
                                continue
                            index = row_idx * len(row) + col_idx
                            if index >= len(table.cells):
                                continue
                            cell_info = table.cells[index]
                            cell_bbox = cell_info.bbox if hasattr(cell_info, "bbox") else cell_info
                            cell_x0, cell_top, cell_x1, cell_bottom = cell_bbox

                            cell_words = [word for word in words if not (
                                word["x1"] < cell_x0 or word["x0"] > cell_x1 or
                                word["bottom"] < cell_top or word["top"] > cell_bottom)]

                            vertical_tolerance = 8.0
                            horizontal_tolerance = 2.0
                            for word in cell_words:
                                if "fontname" in word and "courier" in word["fontname"].lower():
                                    continue
                                word_x0, word_top, word_x1, word_bottom = word["x0"], word["top"], word["x1"], word["bottom"]
                                is_superscript = (abs(word_bottom - cell_bottom) < vertical_tolerance and len(word["text"]) <= 4) or \
                                                 (word_top < cell_top - vertical_tolerance and len(word["text"]) <= 3)
                                if is_superscript:
                                    continue
                                overflow = (word_x0 < cell_x0 - horizontal_tolerance or
                                            word_x1 > cell_x1 + horizontal_tolerance or
                                            word_top < cell_top - vertical_tolerance or
                                            word_bottom > cell_bottom + vertical_tolerance)
                                if overflow:
                                    overflow_page_labels.append(page_label)
                                    break
                except Exception as e:
                    logging.error(f"Error processing table {table_idx} on page {page_label}: {str(e)}")
    except Exception as e:
        logging.error(f"Error processing page {page_num + 1}: {str(e)}")
    finally:
        doc.close()
    return overflow_page_labels

def check_table_overflow(pdf_path):
    """Check for table overflows in the PDF."""
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        label_map = {i: doc[i].get_label() or str(i + 1) for i in range(total_pages)}
        doc.close()

        batch_size = 500
        args = [(pdf_path, i, total_pages) for i in range(total_pages)]
        with Pool() as pool:
            results = []
            for start in range(0, total_pages, batch_size):
                batch_args = args[start:start + batch_size]
                results.extend(pool.map(process_page, batch_args))

        overflow_page_labels = list(set(label for sublist in results for label in sublist))
        overflow_page_labels.sort(key=lambda x: (0, int(x)) if x.isdigit() else (1, x.lower()))
        return overflow_page_labels
    except Exception as e:
        logging.error(f"Top-level error: {str(e)}")
        return []

def main(pdf_path):
    """Main function to check table overflows."""
    overflow_page_labels = check_table_overflow(pdf_path)
    print(json.dumps({"result": overflow_page_labels}, ensure_ascii=False), file=sys.stdout)
    sys.stdout.flush()
    sys.exit(0)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: python verify_pdf_tables.py <pdf_path>"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    pdf_path = sys.argv[1]
    main(pdf_path)