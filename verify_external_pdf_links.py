import sys
import json
import fitz  # PyMuPDF
import asyncio
import httpx
from urllib.parse import unquote

CONCURRENT_LIMIT = 100  # Control how many requests run in parallel
TIMEOUT = 10  # Seconds

def extract_links(pdf_path):
    """Extract annotation-based hyperlinks from the PDF using PyMuPDF."""
    hyperlinks = {}  # Map of URL to list of page labels

    # Step 1: Extract annotation-based hyperlinks using PyMuPDF
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        for page_num in range(total_pages):
            print(json.dumps({"progress": f"Extracting hyperlinks: Page {page_num + 1}/{total_pages}"}))
            sys.stdout.flush()
            page = doc[page_num]
            # Get the page label (e.g., "i", "5") instead of physical page number
            page_label = page.get_label() or str(page_num + 1)  # Fallback to physical page number if label not defined
            for link in page.get_links():
                uri = link.get("uri")
                if uri:
                    if uri in hyperlinks:
                        if page_label not in hyperlinks[uri]:
                            hyperlinks[uri].append(page_label)
                    else:
                        hyperlinks[uri] = [page_label]
        doc.close()
    except Exception as e:
        print(f"Error extracting hyperlinks: {str(e)}", file=sys.stderr)

    print(f"DEBUG: Total Hyperlinks Extracted={len(hyperlinks)}, URLs={list(hyperlinks.keys())}", file=sys.stderr)
    return hyperlinks

async def check_link_validity(url, pages, client, sem):
    """Check if a hyperlink is valid by making an HTTP request, and detect redirects."""
    async with sem:  # Limit concurrency
        try:
            response = await client.head(url, follow_redirects=False, timeout=TIMEOUT)
            if response.status_code in (301, 302):
                redirected_url = response.headers.get("Location", "")
                print(f"DEBUG: URL={url}, Status={response.status_code}, Redirected To={redirected_url}", file=sys.stderr)
                return {"url": url, "pages": pages, "reason": f"Redirected, Status: {response.status_code}", "redirected_to": redirected_url}, "redirected"
            elif response.status_code >= 400:
                print(f"DEBUG: URL={url}, Status={response.status_code}", file=sys.stderr)
                return {"url": url, "pages": pages, "reason": f"Status: {response.status_code}"}, "invalid"
            else:
                print(f"DEBUG: URL={url}, Status={response.status_code}", file=sys.stderr)
                return {"url": url, "pages": pages, "reason": f"Valid, Status: {response.status_code}"}, "valid"
        except httpx.TimeoutException:
            print(f"DEBUG: URL={url}, Timeout", file=sys.stderr)
            return {"url": url, "pages": pages, "reason": "Timeout"}, "unreachable"
        except Exception as e:
            print(f"DEBUG: URL={url}, Error={str(e)}", file=sys.stderr)
            return {"url": url, "pages": pages, "reason": f"Error: {str(e)}"}, "unreachable"

async def validate_all_links(hyperlinks):
    """Validate all unique links concurrently."""
    invalid_links = []
    redirected_links = []
    unreachable_links = []
    valid_links = []  # For debugging, to confirm valid links
    total_links = sum(len(pages) for pages in hyperlinks.values())
    checked = 0
    unique_urls = list(hyperlinks.keys())

    sem = asyncio.Semaphore(CONCURRENT_LIMIT)
    async with httpx.AsyncClient() as client:
        tasks = []
        for url in unique_urls:
            tasks.append(check_link_validity(url, hyperlinks[url], client, sem))

        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    print(f"DEBUG: Validation Error={str(result)}", file=sys.stderr)
                    continue
                
                link_info, category = result
                checked += 1
                print(json.dumps({"progress": f"Checking links: {checked}/{len(unique_urls)}"}))
                sys.stdout.flush()
                print(f"DEBUG: URL={link_info['url']}, Category={category}, Reason={link_info['reason']}", file=sys.stderr)
                if category == "redirected":
                    redirected_links.append(link_info)
                elif category == "invalid":
                    invalid_links.append(link_info)
                elif category == "unreachable":
                    unreachable_links.append(link_info)
                elif category == "valid":
                    valid_links.append(link_info)  # For debugging

        except Exception as e:
            print(f"DEBUG: Validation Error={str(e)}", file=sys.stderr)

    print(f"DEBUG: Validation Complete, Total Checked={checked}, Valid Links={len(valid_links)}", file=sys.stderr)
    return {
        "total_links": total_links,
        "redirected": redirected_links,
        "invalid": invalid_links,
        "unreachable": unreachable_links
    }

def main(pdf_path):
    """Main function to validate external PDF links."""
    hyperlinks = extract_links(pdf_path)
    if not hyperlinks:
        result = {"total_links": 0, "redirected": [], "invalid": [], "unreachable": []}
    else:
        # Run the asynchronous link validation using asyncio.run
        result = asyncio.run(validate_all_links(hyperlinks))
    print(json.dumps({"result": result}))
    sys.stdout.flush()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python verify_external_pdf_links.py <pdf_path>", file=sys.stderr)
        sys.exit(1)
    pdf_path = sys.argv[1]
    main(pdf_path)