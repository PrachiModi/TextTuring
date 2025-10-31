import sys
import json
import fitz
import requests
from urllib.parse import unquote
import time
import logging
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import signal
from multiprocessing import cpu_count

# Debug: Print environment details
print(f"validate_external_pdf_links.py: Python executable: {sys.executable}", flush=True)
print(f"validate_external_pdf_links.py: Working directory: {os.getcwd()}", flush=True)
try:
    import fitz
    print(f"validate_external_pdf_links.py: PyMuPDF version: {fitz.__version__}", flush=True)
except ImportError as e:
    print(f"validate_external_pdf_links.py: ImportError: {str(e)}", file=sys.stderr, flush=True)
    logger.error(f"ImportError: {str(e)}")

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s',
    handlers=[logging.FileHandler('validation.log', mode='a')]
)
logger = logging.getLogger(__name__)

CONCURRENT_LIMIT = 100  # Increased for faster parallel validation
TIMEOUT = 1.5  # Reduced for faster failure detection
URL_CACHE = {}
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def signal_handler(sig, frame):
    """Handle termination signals."""
    logger.error(f"Received signal: {sig}")
    sys.exit(1)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def process_page_optimized(args):
    """
    Process a single PDF page to extract external and mailto links.
    Optimized version that opens the PDF once per thread.
    
    Args:
        args: Tuple of (page_num, pdf_path, total_pages)
        
    Returns:
        Tuple of (external_links_page, mailto_links_page, page_num)
    """
    page_num, pdf_path, total_pages = args
    logger.debug(f"Processing page {page_num + 1}/{total_pages}")
    try:
        # Open PDF in this thread (not in main process)
        doc = fitz.open(pdf_path)
        page = doc[page_num]
        page_label = page.get_label() or str(page_num + 1)
        external_links = defaultdict(int)
        mailto_links = defaultdict(int)
        
        for link in page.get_links():
            uri = link.get("uri")
            if uri:
                uri = unquote(uri)
                # Skip text extraction - not needed for validation (major speedup)
                if uri.startswith("mailto:"):
                    mailto_links[uri] += 1
                elif uri.startswith(("http:", "https:")):
                    external_links[uri] += 1
        
        external_links_page = {uri: (page_label, count) for uri, count in external_links.items()}
        mailto_links_page = {uri: (page_label, count) for uri, count in mailto_links.items()}
        doc.close()
        
        logger.debug(f"Page {page_num + 1} processed: {len(external_links)} external, {len(mailto_links)} mailto links")
        return external_links_page, mailto_links_page, page_num
    except Exception as e:
        logger.error(f"Error processing page {page_num + 1}: {str(e)}")
        return {}, {}, page_num

def extract_links(doc, use_multiprocessing=True):
    """
    Extract external and mailto hyperlinks from the PDF using parallel processing.
    
    Args:
        doc: PDF document object
        use_multiprocessing: Whether to use parallel processing (default: True)
        
    Returns:
        Tuple of (external_links, mailto_links)
    """
    logger.debug("Starting link extraction")
    external_links = defaultdict(Counter)
    mailto_links = defaultdict(Counter)
    
    try:
        total_pages = len(doc)
        pdf_path = doc.name
        
        # Prepare page processing tasks
        page_tasks = [(i, pdf_path, total_pages) for i in range(total_pages)]
        
        if use_multiprocessing and total_pages > 1:
            # Use ThreadPoolExecutor for parallel page processing
            # Threads are better than processes here because:
            # 1. PDF operations are I/O bound
            # 2. fitz objects can't be easily pickled
            # Scale workers based on PDF size for optimal performance
            if total_pages > 1000:
                # For very large PDFs (>1000 pages), use more workers
                max_workers = min(cpu_count() * 4, total_pages, 32)
            else:
                max_workers = min(cpu_count() * 2, total_pages, 16)
            logger.debug(f"Processing {total_pages} pages with {max_workers} workers")
            
            completed_pages = 0
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all tasks
                futures = {executor.submit(process_page_optimized, task): task for task in page_tasks}
                
                # Process results as they complete
                for future in as_completed(futures):
                    try:
                        ext, mail, page_num = future.result()
                        
                        # Merge results
                        for uri, (page, count) in ext.items():
                            external_links[uri][page] += count
                        for uri, (page, count) in mail.items():
                            mailto_links[uri][page] += count
                        
                        completed_pages += 1
                        # Adjust progress frequency based on PDF size
                        progress_interval = max(10, total_pages // 100)  # Report every 1% for large PDFs
                        if completed_pages % progress_interval == 0 or completed_pages == total_pages:
                            percentage = (completed_pages / total_pages) * 100
                            print(f"Progress: Processing page ({completed_pages}/{total_pages}) - {percentage:.1f}%", flush=True)
                        sys.stdout.flush()
                    except Exception as e:
                        logger.error(f"Error processing page result: {str(e)}")
        else:
            # Single-threaded fallback
            logger.debug(f"Processing {total_pages} pages sequentially")
            for i, task in enumerate(page_tasks):
                ext, mail, page_num = process_page_optimized(task)
                for uri, (page, count) in ext.items():
                    external_links[uri][page] += count
                for uri, (page, count) in mail.items():
                    mailto_links[uri][page] += count
                
                progress_interval = max(10, total_pages // 100)
                if (i + 1) % progress_interval == 0 or (i + 1) == total_pages:
                    percentage = ((i + 1) / total_pages) * 100
                    print(f"Progress: Processing page ({i + 1}/{total_pages}) - {percentage:.1f}%", flush=True)
                sys.stdout.flush()
        
        logger.debug(f"Extracted {len(external_links)} unique external links and {len(mailto_links)} unique mailto links")
    except Exception as e:
        logger.error(f"Error extracting hyperlinks: {str(e)}")
        print(f"Error extracting hyperlinks: {str(e)}", file=sys.stderr, flush=True)
    
    return external_links, mailto_links

def check_link_validity(url, pages_counts, session):
    """Check if an external hyperlink is valid, skip GET on HEAD timeout."""
    if url in URL_CACHE:
        return URL_CACHE[url]

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        response = session.head(url, allow_redirects=False, timeout=TIMEOUT, headers=headers)
        
        if response.status_code in (301, 302):
            redirected_url = response.headers.get("Location", "")
            result = ({"url": url, "pages_counts": dict(pages_counts), "reason": f"Redirected, Status: {response.status_code}", "redirected_to": redirected_url}, "redirected")
            URL_CACHE[url] = result
            return result
        elif response.status_code >= 400:
            result = ({"url": url, "pages_counts": dict(pages_counts), "reason": f"Status: {response.status_code}"}, "invalid")
            URL_CACHE[url] = result
            return result
        else:
            result = ({"url": url, "pages_counts": dict(pages_counts), "reason": f"Valid, Status: {response.status_code}"}, "valid")
            URL_CACHE[url] = result
            return result
    
    except requests.Timeout:
        result = ({"url": url, "pages_counts": dict(pages_counts), "reason": f"Timeout after {TIMEOUT}s"}, "unreachable")
        URL_CACHE[url] = result
        return result
    except Exception as e:
        result = ({"url": url, "pages_counts": dict(pages_counts), "reason": f"Error: {str(e)}"}, "unreachable")
        URL_CACHE[url] = result
        return result

def validate_all_links(external_links):
    """Validate all unique external links concurrently using threads."""
    logger.debug(f"Starting validation of {len(external_links)} unique URLs")
    invalid_links = []
    redirected_links = []
    unreachable_links = []
    valid_links = []
    unique_urls = list(external_links.keys())
    batch_size = 50

    with requests.Session() as session:
        # Optimize session for high concurrency
        session.max_retries = 0
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=CONCURRENT_LIMIT,
            pool_maxsize=CONCURRENT_LIMIT * 2,
            max_retries=0
        )
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        with ThreadPoolExecutor(max_workers=CONCURRENT_LIMIT) as executor:
            for i in range(0, len(unique_urls), batch_size):
                batch_urls = unique_urls[i:i + batch_size]
                logger.debug(f"Processing batch {i//batch_size + 1} with {len(batch_urls)} URLs")
                results = list(executor.map(lambda url: check_link_validity(url, external_links[url], session), batch_urls))
                for result in results:
                    if isinstance(result, Exception):
                        logger.error(f"Validation error: {str(result)}")
                        continue
                    
                    link_info, category = result
                    logger.debug(f"URL={link_info['url']}, Category={category}, Reason={link_info['reason']}")
                    if category == "redirected":
                        redirected_links.append(link_info)
                    elif category == "invalid":
                        invalid_links.append(link_info)
                    elif category == "unreachable":
                        unreachable_links.append(link_info)
                    elif category == "valid":
                        valid_links.append(link_info)
                print(f"Progress: Validated {i + len(batch_urls)}/{len(unique_urls)} URLs", flush=True)
                # Stream partial results
                partial_result = {
                    "total_links": sum(sum(counter.values()) for counter in external_links.values()),
                    "redirected": redirected_links,
                    "invalid": invalid_links,
                    "unreachable": unreachable_links
                }
                try:
                    partial_file = os.path.join(SCRIPT_DIR, 'validation_result_partial.json')
                    with open(partial_file, 'w', encoding='utf-8') as f:
                        json.dump({"partial_result": partial_result}, f, ensure_ascii=False)
                    logger.debug(f"Partial result written to {partial_file} for batch {i//batch_size + 1}")
                    print(f"Partial result written to {partial_file}", file=sys.stderr, flush=True)
                except Exception as e:
                    logger.error(f"Error writing partial result to {partial_file}: {str(e)}")
                    print(f"Error writing partial result: {str(e)}", file=sys.stderr, flush=True)

    logger.debug(f"Validation complete: Valid={len(valid_links)}, Redirected={len(redirected_links)}, Invalid={len(invalid_links)}, Unreachable={len(unreachable_links)}")
    return {
        "total_links": sum(sum(counter.values()) for counter in external_links.values()),
        "redirected": redirected_links,
        "invalid": invalid_links,
        "unreachable": unreachable_links
    }

def main(pdf_path):
    """Main function to validate external PDF links and collect mailto links."""
    logger.debug(f"Starting PDF link validation for {pdf_path}")
    result = {}
    try:
        logger.debug("Opening PDF document")
        doc = fitz.open(pdf_path)
        logger.debug("Extracting links")
        external_links, mailto_links = extract_links(doc)
        total_mailto_links = sum(sum(counter.values()) for counter in mailto_links.values())
        logger.debug(f"Total mailto links: {total_mailto_links}")
        if external_links:
            logger.debug("Validating external links")
            external_result = validate_all_links(external_links)
            logger.debug("External link validation completed")
        else:
            external_result = {"total_links": 0, "redirected": [], "invalid": [], "unreachable": []}
            logger.debug("No external links found")
        result = {
            "total_links": external_result["total_links"] + total_mailto_links,
            "redirected": external_result["redirected"],
            "invalid": external_result["invalid"],
            "unreachable": external_result["unreachable"],
            "mailto_count": len(mailto_links)
        }
        logger.debug(f"Final result: {json.dumps(result, ensure_ascii=False)}")
        # Write result to file first as a fallback
        try:
            result_file = os.path.join(SCRIPT_DIR, 'validation_result.json')
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump({"result": result}, f, ensure_ascii=False)
            logger.debug(f"Result written to {result_file}")
            print(f"Result written to {result_file}", file=sys.stderr, flush=True)
        except Exception as e:
            logger.error(f"Error writing to {result_file}: {str(e)}")
            print(f"Error writing to {result_file}: {str(e)}", file=sys.stderr, flush=True)
    except Exception as e:
        logger.error(f"Validation error in main: {str(e)}")
        result = {"error": str(e)}
        try:
            result_file = os.path.join(SCRIPT_DIR, 'validation_result.json')
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump({"result": result}, f, ensure_ascii=False)
            logger.debug(f"Error result written to {result_file}")
            print(f"Error result written to {result_file}", file=sys.stderr, flush=True)
        except Exception as e:
            logger.error(f"Error writing error result to {result_file}: {str(e)}")
            print(f"Error writing error result to {result_file}: {str(e)}", file=sys.stderr, flush=True)
        print(json.dumps({"result": result}, ensure_ascii=False), file=sys.stderr, flush=True)
    finally:
        if 'doc' in locals():
            doc.close()
            logger.debug("PDF document closed")
    try:
        logger.debug("Outputting JSON result to stdout")
        print(json.dumps({"result": result}, ensure_ascii=False), file=sys.stdout, flush=True)
        logger.debug("JSON output flushed")
        sys.stdout.flush()
    except BrokenPipeError as e:
        logger.error(f"Broken pipe error when outputting JSON to stdout: {str(e)}")
        print(f"Broken pipe error: {str(e)}", file=sys.stderr, flush=True)
    logger.debug(f"Completed PDF link validation for {pdf_path}")

if __name__ == "__main__":
    logger.debug("Script started")
    if len(sys.argv) != 2:
        error_msg = "Usage: python validate_external_pdf_links.py <pdf_path>"
        logger.error(error_msg)
        print(json.dumps({"error": error_msg}, ensure_ascii=False), file=sys.stderr, flush=True)
        try:
            result_file = os.path.join(SCRIPT_DIR, 'validation_result.json')
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump({"error": error_msg}, f, ensure_ascii=False)
            logger.debug(f"Error result written to {result_file}")
            print(f"Error result written to {result_file}", file=sys.stderr, flush=True)
        except Exception as e:
            logger.error(f"Error writing error result to {result_file}: {str(e)}")
            print(f"Error writing error result to {result_file}: {str(e)}", file=sys.stderr, flush=True)
        sys.exit(1)
    pdf_path = sys.argv[1]
    logger.debug(f"Processing PDF: {pdf_path}")
    main(pdf_path)
    logger.debug("Script completed")