import sys
import json
import fitz
import asyncio
import httpx
from urllib.parse import unquote
import time
import logging
from multiprocessing import Pool
from functools import partial

# Set up logging to a file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s',
    handlers=[logging.FileHandler('validation.log', mode='a')]
)
logger = logging.getLogger(__name__)

CONCURRENT_LIMIT = 100
TIMEOUT = 10
URL_CACHE = {}

def process_page(page_num, pdf_path):
    """Process a single PDF page to extract external and mailto links."""
    try:
        doc = fitz.open(pdf_path)
        page = doc[page_num]
        page_label = page.get_label() or str(page_num + 1)
        external_links = {}
        mailto_links = {}
        for link in page.get_links():
            uri = link.get("uri")
            if uri:
                uri = unquote(uri)
                if uri.startswith("mailto:"):
                    mailto_links.setdefault(uri, []).append(page_label)
                elif uri.startswith(("http:", "https:")):
                    external_links.setdefault(uri, []).append(page_label)
        doc.close()
        return external_links, mailto_links
    except Exception as e:
        logger.error(f"Error processing page {page_num + 1}: {str(e)}")
        return {}, {}

def extract_links(doc):
    """Extract external and mailto hyperlinks from the PDF using multiprocessing."""
    logger.info("Starting link extraction")
    external_links = {}
    mailto_links = {}
    try:
        total_pages = len(doc)
        with Pool() as pool:
            results = pool.map(partial(process_page, pdf_path=doc.name), range(total_pages))
        for ext_links, mail_links in results:
            for uri, pages in ext_links.items():
                external_links.setdefault(uri, []).extend(pages)
            for uri, pages in mail_links.items():
                mailto_links.setdefault(uri, []).extend(pages)
        logger.info(f"Extracted {len(external_links)} external links and {len(mailto_links)} mailto links")
    except Exception as e:
        logger.error(f"Error extracting hyperlinks: {str(e)}")
        print(f"Error extracting hyperlinks: {str(e)}", file=sys.stderr)
    return external_links, mailto_links

async def check_link_validity(url, pages, client, sem):
    """Check if an external hyperlink is valid, with retries and GET fallback."""
    logger.debug(f"Checking URL: {url}")
    if url in URL_CACHE:
        logger.debug(f"Using cached result for {url}")
        return URL_CACHE[url]

    async with sem:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        attempts = 0
        max_attempts = 3
        while attempts < max_attempts:
            attempts += 1
            try:
                start_time = time.time()
                response = await client.head(url, follow_redirects=False, timeout=TIMEOUT, headers=headers)
                duration = time.time() - start_time
                logger.debug(f"URL={url}, Attempt={attempts}, Method=HEAD, Status={response.status_code}, Duration={duration:.3f}s")
                
                if response.status_code in (301, 302):
                    redirected_url = response.headers.get("Location", "")
                    result = ({"url": url, "pages": pages, "reason": f"Redirected, Status: {response.status_code}", "redirected_to": redirected_url}, "redirected")
                    URL_CACHE[url] = result
                    return result
                elif response.status_code >= 400:
                    result = ({"url": url, "pages": pages, "reason": f"Status: {response.status_code}"}, "invalid")
                    URL_CACHE[url] = result
                    return result
                else:
                    result = ({"url": url, "pages": pages, "reason": f"Valid, Status: {response.status_code}"}, "valid")
                    URL_CACHE[url] = result
                    return result
            
            except httpx.TimeoutException:
                if attempts == max_attempts:
                    logger.debug(f"URL={url}, Attempt={attempts}, Method=HEAD, Timeout after {TIMEOUT}s")
                    try:
                        start_time = time.time()
                        response = await client.get(url, follow_redirects=False, timeout=TIMEOUT, headers=headers)
                        duration = time.time() - start_time
                        logger.debug(f"URL={url}, Attempt={attempts}, Method=GET, Status={response.status_code}, Duration={duration:.3f}s")
                        
                        if response.status_code in (301, 302):
                            redirected_url = response.headers.get("Location", "")
                            result = ({"url": url, "pages": pages, "reason": f"Redirected, Status: {response.status_code}", "redirected_to": redirected_url}, "redirected")
                            URL_CACHE[url] = result
                            return result
                        elif response.status_code >= 400:
                            result = ({"url": url, "pages": pages, "reason": f"Status: {response.status_code}"}, "invalid")
                            URL_CACHE[url] = result
                            return result
                        else:
                            result = ({"url": url, "pages": pages, "reason": f"Valid, Status: {response.status_code}"}, "valid")
                            URL_CACHE[url] = result
                            return result
                    except httpx.TimeoutException:
                        logger.debug(f"URL={url}, Attempt={attempts}, Method=GET, Timeout after {TIMEOUT}s")
                        result = ({"url": url, "pages": pages, "reason": f"Timeout after {TIMEOUT}s"}, "unreachable")
                        URL_CACHE[url] = result
                        return result
                    except Exception as e:
                        logger.debug(f"URL={url}, Attempt={attempts}, Method=GET, Error={str(e)}")
                        result = ({"url": url, "pages": pages, "reason": f"Error: {str(e)}"}, "unreachable")
                        URL_CACHE[url] = result
                        return result
            except Exception as e:
                if attempts == max_attempts:
                    logger.debug(f"URL={url}, Attempt={attempts}, Method=HEAD, Error={str(e)}")
                    result = ({"url": url, "pages": pages, "reason": f"Error: {str(e)}"}, "unreachable")
                    URL_CACHE[url] = result
                    return result
                logger.debug(f"URL={url}, Attempt={attempts}, Method=HEAD, Retrying due to {str(e)}")
                await asyncio.sleep(1)

async def validate_all_links(external_links):
    """Validate all unique external links concurrently."""
    logger.info(f"Starting validation of {len(external_links)} unique URLs")
    invalid_links = []
    redirected_links = []
    unreachable_links = []
    valid_links = []
    unique_urls = list(external_links.keys())

    sem = asyncio.Semaphore(CONCURRENT_LIMIT)
    async with httpx.AsyncClient() as client:
        tasks = []
        for url in unique_urls:
            tasks.append(check_link_validity(url, external_links[url], client, sem))

        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
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

        except Exception as e:
            logger.error(f"Validation error: {str(e)}")

    logger.info(f"Validation complete: Valid={len(valid_links)}, Redirected={len(redirected_links)}, Invalid={len(invalid_links)}, Unreachable={len(unreachable_links)}")
    return {
        "total_links": sum(len(pages) for pages in external_links.values()),
        "redirected": redirected_links,
        "invalid": invalid_links,
        "unreachable": unreachable_links
    }

def main(pdf_path):
    """Main function to validate external PDF links and collect mailto links."""
    logger.info(f"Starting PDF link validation for {pdf_path}")
    result = {}
    try:
        doc = fitz.open(pdf_path)
        external_links, mailto_links = extract_links(doc)
        total_mailto_links = sum(len(pages) for pages in mailto_links.values())
        if external_links:
            external_result = asyncio.run(validate_all_links(external_links))
        else:
            external_result = {"total_links": 0, "redirected": [], "invalid": [], "unreachable": []}
        result = {
            "total_links": external_result["total_links"] + total_mailto_links,
            "redirected": external_result["redirected"],
            "invalid": external_result["invalid"],
            "unreachable": external_result["unreachable"],
            "mailto_count": len(mailto_links)  # Report number of unique mailto links
        }
    except Exception as e:
        logger.error(f"Validation error: {str(e)}")
        result = {"error": str(e)}
    finally:
        if 'doc' in locals():
            doc.close()
    print(json.dumps({"result": result}, ensure_ascii=False), file=sys.stdout)
    sys.stdout.flush()
    logger.info(f"Completed PDF link validation for {pdf_path}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        error_msg = "Usage: python verify_external_pdf_links.py <pdf_path>"
        logger.error(error_msg)
        print(json.dumps({"error": error_msg}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    pdf_path = sys.argv[1]
    main(pdf_path)