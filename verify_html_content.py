import sys
import json
import os
import platform
import threading
import logging
from pathlib import Path
from lxml import etree
from lxml import html
from urllib.parse import unquote
import glob
import requests
from concurrent.futures import ThreadPoolExecutor
import time

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s',
    handlers=[logging.FileHandler('validation.log', mode='w')]
)
logger = logging.getLogger(__name__)

CONCURRENT_LIMIT = 50  # Reduced for balanced performance
TIMEOUT = 5  # Reduced for faster failure on unreachable URLs
URL_CACHE = {}

def timeout_handler():
    raise TimeoutError("File processing timed out")

def check_link_validity(url, files, session):
    """Check if an external hyperlink is valid, with GET fallback."""
    logger.debug(f"Checking URL: {url}")
    if url in URL_CACHE:
        logger.debug(f"Using cached result for {url}")
        return URL_CACHE[url]

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        start_time = time.time()
        response = session.head(url, allow_redirects=False, timeout=TIMEOUT, headers=headers)
        duration = time.time() - start_time
        logger.debug(f"URL={url}, Method=HEAD, Status={response.status_code}, Duration={duration:.3f}s")
        
        if response.status_code in (301, 302):
            redirected_url = response.headers.get("Location", "")
            result = ({"url": url, "files": files, "reason": f"Redirected, Status: {response.status_code}", "redirected_to": redirected_url}, "redirected")
            URL_CACHE[url] = result
            return result
        elif response.status_code >= 400:
            result = ({"url": url, "files": files, "reason": f"Status: {response.status_code}"}, "invalid")
            URL_CACHE[url] = result
            return result
        else:
            result = ({"url": url, "files": files, "reason": f"Valid, Status: {response.status_code}"}, "valid")
            URL_CACHE[url] = result
            return result
    
    except requests.Timeout:
        logger.debug(f"URL={url}, Method=HEAD, Timeout after {TIMEOUT}s")
        try:
            start_time = time.time()
            response = session.get(url, allow_redirects=False, timeout=TIMEOUT, headers=headers)
            duration = time.time() - start_time
            logger.debug(f"URL={url}, Method=GET, Status={response.status_code}, Duration={duration:.3f}s")
            
            if response.status_code in (301, 302):
                redirected_url = response.headers.get("Location", "")
                result = ({"url": url, "files": files, "reason": f"Redirected, Status: {response.status_code}", "redirected_to": redirected_url}, "redirected")
                URL_CACHE[url] = result
                return result
            elif response.status_code >= 400:
                result = ({"url": url, "files": files, "reason": f"Status: {response.status_code}"}, "invalid")
                URL_CACHE[url] = result
                return result
            else:
                result = ({"url": url, "files": files, "reason": f"Valid, Status: {response.status_code}"}, "valid")
                URL_CACHE[url] = result
                return result
        except requests.Timeout:
            logger.debug(f"URL={url}, Method=GET, Timeout after {TIMEOUT}s")
            result = ({"url": url, "files": files, "reason": f"Timeout after {TIMEOUT}s"}, "unreachable")
            URL_CACHE[url] = result
            return result
        except Exception as e:
            logger.debug(f"URL={url}, Method=GET, Error={str(e)}")
            result = ({"url": url, "files": files, "reason": f"Error: {str(e)}"}, "unreachable")
            URL_CACHE[url] = result
            return result
    except Exception as e:
        logger.debug(f"URL={url}, Method=HEAD, Error={str(e)}")
        result = ({"url": url, "files": files, "reason": f"Error: {str(e)}"}, "unreachable")
        URL_CACHE[url] = result
        return result

def validate_all_external_links(external_links):
    """Validate all unique external links concurrently in batches."""
    logger.info(f"Starting validation of {len(external_links)} unique URLs")
    invalid_links = []
    redirected_links = []
    unreachable_links = []
    valid_links = []
    unique_urls = list(external_links.keys())
    batch_size = 100

    with requests.Session() as session:
        with ThreadPoolExecutor(max_workers=CONCURRENT_LIMIT) as executor:
            for i in range(0, len(unique_urls), batch_size):
                batch_urls = unique_urls[i:i + batch_size]
                results = list(executor.map(lambda url: check_link_validity(url, list(set(external_links[url])), session), batch_urls))
                logger.debug(f"Processing batch {i//batch_size + 1} with {len(batch_urls)} URLs")
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

    logger.info(f"Validation complete: Valid={len(valid_links)}, Redirected={len(redirected_links)}, Invalid={len(invalid_links)}, Unreachable={len(unreachable_links)}")
    return {
        "total_external_links": sum(len(files) for files in external_links.values()),
        "redirected": redirected_links,
        "invalid": invalid_links,
        "unreachable": unreachable_links
    }

def validate_links_and_images(html_path):
    """Validate internal links, images, and external links in HTML files."""
    logger.info(f"Starting validation for {html_path}")
    total_links = 0
    total_images = 0
    total_external_links = 0
    link_issues = []
    image_issues = []
    external_links = {}
    base_dir = Path(html_path).parent
    graphics_dir = base_dir / "Graphics"
    path_cache = {}

    path_mappings = {
        "Chapter - What's New": "Chapter - Whats New",
        "Chapter - Whats New": "Chapter - Whats New",
        "Chapter - What's New in this Guide": "Chapter - Whats New in this Guide",
        "Chapter - Whats New in this Guide": "Chapter - Whats New in this Guide",
        "Chapter - What's New in This Guide": "Chapter - Whats New in this Guide"
    }

    if not graphics_dir.exists():
        error_msg = f"Graphics folder not found at {graphics_dir}"
        logger.error(error_msg)
        return {"error": error_msg}

    html_files = (
        [str(Path(html_path))] +
        list(glob.glob(str(base_dir / "**" / "*.html"), recursive=True)) +
        list(glob.glob(str(base_dir / "**" / "*.HTML"), recursive=True))
    )
    html_files = [Path(f) for f in sorted(set(html_files))]
    total_files = len(html_files)
    logger.info(f"Found {total_files} HTML files")

    if not html_files:
        logger.warning("No HTML files found in project directory")
        return {"error": "No valid HTML files found"}

    for html_file in html_files:
        file_path = str(html_file)
        logger.debug(f"Processing HTML file: {html_file.name}")

        try:
            timer = threading.Timer(120, timeout_handler)
            timer.start()
            parser = etree.HTMLParser(recover=True)
            with open(html_file, 'rb') as f:
                tree = html.parse(f, parser=parser)

            # Validate internal links and collect external links
            links = tree.xpath("//a[@href]")
            total_links += len(links)
            logger.debug(f"Found {len(links)} links in {html_file.name}")

            file_added = set()
            for link in links:
                href = link.get("href")
                if not href:
                    continue
                if href.startswith(("http://", "https://")):
                    href = unquote(href)
                    file_path_str = str(html_file.relative_to(base_dir))
                    if (href, file_path_str) not in file_added:
                        external_links.setdefault(href, []).append(file_path_str)
                        file_added.add((href, file_path_str))
                    continue

                try:
                    decoded_href = unquote(href.split('#')[0])
                    mapped_href = decoded_href
                    for old_path, new_path in path_mappings.items():
                        if old_path in mapped_href:
                            mapped_href = mapped_href.replace(old_path, new_path)

                    if mapped_href in path_cache:
                        target_path = path_cache[mapped_href]
                    else:
                        html_dir = html_file.parent
                        target_path = (html_dir / mapped_href).resolve()
                        path_cache[mapped_href] = target_path

                    if not str(target_path).startswith(str(base_dir)):
                        link_issues.append({
                            "file": html_file.name,
                            "href": href,
                            "location": str(html_file.relative_to(base_dir)),
                            "issue": "Link points outside project directory"
                        })
                        continue

                    if not target_path.exists():
                        parent_dir = target_path.parent
                        target_name = target_path.name
                        for existing_file in parent_dir.glob("*"):
                            if existing_file.name.lower() == target_name.lower():
                                target_path = existing_file
                                path_cache[mapped_href] = target_path
                                break
                        if not target_path.exists():
                            link_issues.append({
                                "file": html_file.name,
                                "href": href,
                                "location": str(html_file.relative_to(base_dir)),
                                "issue": f"Target file does not exist: {target_path}"
                            })

                except (ValueError, OSError) as e:
                    link_issues.append({
                        "file": html_file.name,
                        "href": href,
                        "location": str(html_file.relative_to(base_dir)),
                        "issue": f"Invalid path in href: {str(e)}"
                    })

            # Validate images
            images = tree.xpath("//img[@src]")
            total_images += len(images)
            logger.debug(f"Found {len(images)} images in {html_file.name}")

            for img in images:
                src = img.get("src")
                if not src:
                    continue

                try:
                    decoded_href = unquote(src)
                    if decoded_href in path_cache:
                        target_path = path_cache[decoded_href]
                    else:
                        html_dir = html_file.parent
                        target_path = (html_dir / decoded_href).resolve()
                        path_cache[decoded_href] = target_path

                    if not str(target_path).startswith(str(graphics_dir)):
                        image_issues.append({
                            "file": html_file.name,
                            "src": src,
                            "location": str(html_file.relative_to(base_dir)),
                            "issue": f"Image points outside Graphics folder: {target_path}"
                        })
                        continue

                    if not target_path.exists():
                        image_issues.append({
                            "file": html_file.name,
                            "src": src,
                            "location": str(html_file.relative_to(base_dir)),
                            "issue": f"Image file does not exist: {target_path}"
                        })

                except (ValueError, OSError) as e:
                    image_issues.append({
                        "file": html_file.name,
                        "src": src,
                        "location": str(html_file.relative_to(base_dir)),
                        "issue": f"Invalid path in src: {str(e)}"
                    })

            timer.cancel()

        except TimeoutError:
            logger.error(f"Timeout processing {html_file.name}")
            link_issues.append({
                "file": html_file.name,
                "href": "N/A",
                "location": str(html_file.relative_to(base_dir)),
                "issue": "File processing timed out"
            })
            image_issues.append({
                "file": html_file.name,
                "src": "N/A",
                "location": str(html_file.relative_to(base_dir)),
                "issue": "File processing timed out"
            })
            timer.cancel()

        except html.HtmlParsingError as e:
            logger.error(f"Error parsing {html_file.name}: {str(e)}")
            link_issues.append({
                "file": html_file.name,
                "href": "N/A",
                "location": str(html_file.relative_to(base_dir)),
                "issue": f"Error parsing HTML: {str(e)}"
            })
            image_issues.append({
                "file": html_file.name,
                "src": "N/A",
                "location": str(html_file.relative_to(base_dir)),
                "issue": f"Error parsing HTML: {str(e)}"
            })

        except Exception as e:
            logger.error(f"Unexpected error processing {html_file.name}: {str(e)}")
            link_issues.append({
                "file": html_file.name,
                "href": "N/A",
                "location": str(html_file.relative_to(base_dir)),
                "issue": f"Unexpected error: {str(e)}"
            })
            image_issues.append({
                "file": html_file.name,
                "src": "N/A",
                "location": str(html_file.relative_to(base_dir)),
                "issue": f"Unexpected error: {str(e)}"
            })

    # Validate external links
    external_result = {}
    if external_links:
        try:
            external_result = validate_all_external_links(external_links)
            total_external_links = external_result.get("total_external_links", 0)
        except Exception as e:
            logger.error(f"External link validation failed: {str(e)}")
            external_result = {"error": f"External link validation failed: {str(e)}"}

    logger.info(f"Validation complete: {total_links} internal links, {total_images} images, {total_external_links} external links, {len(link_issues)} link issues, {len(image_issues)} image issues")
    return {
        "total_internal_links": total_links,
        "total_images": total_images,
        "link_issues": link_issues,
        "image_issues": image_issues,
        "external_links": external_result
    }

def validate_internal_links(html_path, validate_html=True):
    """Validate internal links in HTML or XML/DITA files."""
    logger.info(f"Starting internal links validation for {html_path}, validate_html={validate_html}")
    total_links = 0
    link_issues = []
    base_dir = Path(html_path).parent
    topics_dir = base_dir / "Topics"
    path_cache = {}

    path_mappings = {
        "Chapter - What's New": "Chapter - Whats New",
        "Chapter - Whats New": "Chapter - Whats New",
        "Chapter - What's New in this Guide": "Chapter - Whats New in this Guide",
        "Chapter - Whats New in this Guide": "Chapter - Whats New in this Guide",
        "Chapter - What's New in This Guide": "Chapter - Whats New in this Guide"
    }

    if validate_html:
        logger.info(f"Looking for HTML files in {base_dir}")
        html_files = (
            [str(Path(html_path))] +
            list(glob.glob(str(base_dir / "**" / "*.html"), recursive=True)) +
            list(glob.glob(str(base_dir / "**" / "*.HTML"), recursive=True))
        )
        html_files = [Path(f) for f in sorted(set(html_files))]
        total_files = len(html_files)
        logger.info(f"Found {total_files} HTML files")

        if not html_files:
            logger.warning("No HTML files found in project directory")

        for html_file in html_files:
            file_path = str(html_file)
            logger.info(f"Processing HTML file: {html_file.name}")

            try:
                timer = threading.Timer(50, timeout_handler)
                timer.start()
                parser = etree.HTMLParser(recover=True)
                with open(html_file, 'rb') as f:
                    tree = html.parse(f, parser=parser)
                links = tree.xpath("//a[@href]")
                total_links += len(links)
                logger.info(f"Found {len(links)} links in {html_file.name}")

                for link in links:
                    href = link.get("href")
                    if not href or href.startswith(("http://", "https://")):
                        continue

                    try:
                        decoded_href = unquote(href.split('#')[0])
                        mapped_href = decoded_href
                        for old_path, new_path in path_mappings.items():
                            if old_path in mapped_href:
                                mapped_href = mapped_href.replace(old_path, new_path)

                        if mapped_href in path_cache:
                            target_path = path_cache[mapped_href]
                        else:
                            html_dir = html_file.parent
                            target_path = (html_dir / mapped_href).resolve()
                            path_cache[mapped_href] = target_path

                        if not str(target_path).startswith(str(base_dir)):
                            link_issues.append({
                                "file": html_file.name,
                                "href": href,
                                "location": str(html_file.relative_to(base_dir)),
                                "issue": "Link points outside project directory"
                            })
                            continue

                        if not target_path.exists():
                            parent_dir = target_path.parent
                            target_name = target_path.name
                            for existing_file in parent_dir.glob("*"):
                                if existing_file.name.lower() == target_name.lower():
                                    target_path = existing_file
                                    path_cache[mapped_href] = target_path
                                    break
                            if not target_path.exists():
                                link_issues.append({
                                    "file": html_file.name,
                                    "href": href,
                                    "location": str(html_file.relative_to(base_dir)),
                                    "issue": f"Target file does not exist: {target_path}"
                                })

                    except (ValueError, OSError) as e:
                        link_issues.append({
                            "file": html_file.name,
                            "href": href,
                            "location": str(html_file.relative_to(base_dir)),
                            "issue": f"Invalid path in href: {str(e)}"
                        })

                timer.cancel()

            except TimeoutError:
                logger.error(f"Timeout processing {html_file.name}")
                link_issues.append({
                    "file": html_file.name,
                    "href": "N/A",
                    "location": str(html_file.relative_to(base_dir)),
                    "issue": "File processing timed out"
                })
                timer.cancel()
            except html.HtmlParsingError as e:
                logger.error(f"Error parsing {html_file.name}: {str(e)}")
                link_issues.append({
                    "file": html_file.name,
                    "href": "N/A",
                    "location": str(html_file.relative_to(base_dir)),
                    "issue": f"Error parsing HTML: {str(e)}"
                })
            except Exception as e:
                logger.error(f"Unexpected error processing {html_file.name}: {str(e)}")
                link_issues.append({
                    "file": html_file.name,
                    "href": "N/A",
                    "location": str(html_file.relative_to(base_dir)),
                    "issue": f"Unexpected error: {str(e)}"
                })

    else:
        logger.info(f"Looking for XML/DITA files in {topics_dir} and {base_dir}")
        xml_files = (
            list(glob.glob(str(topics_dir / "**" / "*.xml"), recursive=True)) +
            list(glob.glob(str(topics_dir / "**" / "*.XML"), recursive=True)) +
            list(glob.glob(str(topics_dir / "**" / "*.dita"), recursive=True)) +
            list(glob.glob(str(topics_dir / "**" / "*.DITA"), recursive=True)) +
            list(glob.glob(str(base_dir / "*.ditamap"), recursive=False)) +
            list(glob.glob(str(base_dir / "*.DITAMAP"), recursive=False))
        )
        xml_files = [Path(f) for f in sorted(set(xml_files))]
        total_files = len(xml_files)
        logger.info(f"Found {total_files} XML/DITA files")

        if not xml_files:
            logger.warning("No XML or DITA files found in Topics folder or project root")

        namespaces = {
            'dita': 'http://dita.oasis-open.org/architecture/2005/',
            '': None
        }

        for xml_path in xml_files:
            file_path = str(xml_path)
            logger.info(f"Processing file: {xml_path.name}")

            try:
                timer = threading.Timer(50, timeout_handler)
                timer.start()
                parser = etree.XMLParser(recover=True)
                tree = etree.parse(str(xml_path), parser)
                links = tree.xpath(
                    "//dita:xref[@href] | //xref[@href] | //dita:a[@href] | //a[@href] | //dita:link[@href] | //link[@href] | //dita:topicref[@href] | //topicref[@href]",
                    namespaces=namespaces
                )
                total_links += len(links)
                logger.info(f"Found {len(links)} links in {xml_path.name}")

                for link in links:
                    href = link.get("href")
                    if not href:
                        continue

                    try:
                        decoded_href = unquote(href.split('#')[0])
                        mapped_href = decoded_href
                        for old_path, new_path in path_mappings.items():
                            if old_path in mapped_href:
                                mapped_href = mapped_href.replace(old_path, new_path)

                        if mapped_href in path_cache:
                            target_path = path_cache[mapped_href]
                        else:
                            xml_dir = xml_path.parent
                            target_path = (xml_dir / mapped_href).resolve()
                            path_cache[mapped_href] = target_path

                        if not str(target_path).startswith(str(base_dir)):
                            link_issues.append({
                                "file": xml_path.name,
                                "href": href,
                                "location": str(xml_path.relative_to(base_dir)),
                                "issue": "Link points outside project directory"
                            })
                            continue

                        if not target_path.exists():
                            parent_dir = target_path.parent
                            target_name = target_path.name
                            for existing_file in parent_dir.glob("*"):
                                if existing_file.name.lower() == target_name.lower():
                                    target_path = existing_file
                                    path_cache[mapped_href] = target_path
                                    break
                            if not target_path.exists():
                                link_issues.append({
                                    "file": xml_path.name,
                                    "href": href,
                                    "location": str(xml_path.relative_to(base_dir)),
                                    "issue": f"Target file does not exist: {target_path}"
                                })

                    except (ValueError, OSError) as e:
                        link_issues.append({
                            "file": xml_path.name,
                            "href": href,
                            "location": str(xml_path.relative_to(base_dir)),
                            "issue": f"Invalid path in href: {str(e)}"
                        })

                timer.cancel()

            except TimeoutError:
                logger.error(f"Timeout processing {xml_path.name}")
                link_issues.append({
                    "file": xml_path.name,
                    "href": "N/A",
                    "location": str(xml_path.relative_to(base_dir)),
                    "issue": "File processing timed out"
                })
                timer.cancel()
            except etree.LxmlError as e:
                logger.error(f"Error parsing {xml_path.name}: {str(e)}")
                link_issues.append({
                    "file": xml_path.name,
                    "href": "N/A",
                    "location": str(xml_path.relative_to(base_dir)),
                    "issue": f"Error parsing XML: {str(e)}"
                })
            except Exception as e:
                logger.error(f"Unexpected error processing {xml_path.name}: {str(e)}")
                link_issues.append({
                    "file": xml_path.name,
                    "href": "N/A",
                    "location": str(xml_path.relative_to(base_dir)),
                    "issue": f"Unexpected error: {str(e)}"
                })

    logger.info(f"Validation complete: {total_links} links found, {len(link_issues)} issues")
    return {
        "total_internal_links": total_links,
        "link_issues": link_issues
    }

def validate_images(html_path):
    """Validate images in HTML files."""
    logger.info(f"Starting image validation for {html_path}")
    total_images = 0
    image_issues = []
    base_dir = Path(html_path).parent
    graphics_dir = base_dir / "Graphics"
    path_cache = {}

    if not graphics_dir.exists():
        error_msg = f"Graphics folder not found at {graphics_dir}"
        logger.error(error_msg)
        return {"error": error_msg}

    html_files = (
        [str(Path(html_path))] +
        list(glob.glob(str(base_dir / "**" / "*.html"), recursive=True)) +
        list(glob.glob(str(base_dir / "**" / "*.HTML"), recursive=True))
    )
    html_files = [Path(f) for f in sorted(set(html_files))]
    total_files = len(html_files)
    logger.info(f"Found {total_files} HTML files")

    if not html_files:
        logger.warning("No HTML files found in project directory")

    for html_file in html_files:
        file_path = str(html_file)
        logger.info(f"Processing HTML file: {html_file.name}")

        try:
            timer = threading.Timer(50, timeout_handler)
            timer.start()
            parser = etree.HTMLParser(recover=True)
            with open(html_file, 'rb') as f:
                tree = html.parse(f, parser=parser)
            images = tree.xpath("//img[@src]")
            total_images += len(images)
            logger.info(f"Found {len(images)} images in {html_file.name}")

            for img in images:
                src = img.get("src")
                if not src:
                    continue

                try:
                    decoded_href = unquote(src)
                    if decoded_href in path_cache:
                        target_path = path_cache[decoded_href]
                    else:
                        html_dir = html_file.parent
                        target_path = (html_dir / decoded_href).resolve()
                        path_cache[decoded_href] = target_path

                    if not str(target_path).startswith(str(graphics_dir)):
                        image_issues.append({
                            "file": html_file.name,
                            "src": src,
                            "location": str(html_file.relative_to(base_dir)),
                            "issue": f"Image points outside Graphics folder: {target_path}"
                        })
                        continue

                    if not target_path.exists():
                        image_issues.append({
                            "file": html_file.name,
                            "src": src,
                            "location": str(html_file.relative_to(base_dir)),
                            "issue": f"Image file does not exist: {target_path}"
                        })

                except (ValueError, OSError) as e:
                    image_issues.append({
                        "file": html_file.name,
                        "src": src,
                        "location": str(html_file.relative_to(base_dir)),
                        "issue": f"Invalid path in src: {str(e)}"
                    })

            timer.cancel()

        except TimeoutError:
            logger.error(f"Timeout processing {html_file.name}")
            image_issues.append({
                "file": html_file.name,
                "src": "N/A",
                "location": str(html_file.relative_to(base_dir)),
                "issue": "File processing timed out"
            })
            timer.cancel()
        except html.HtmlParsingError as e:
            logger.error(f"Error parsing {html_file.name}: {str(e)}")
            image_issues.append({
                "file": html_file.name,
                "src": "N/A",
                "location": str(html_file.relative_to(base_dir)),
                "issue": f"Error parsing HTML: {str(e)}"
            })
        except Exception as e:
            logger.error(f"Unexpected error processing {html_file.name}: {str(e)}")
            image_issues.append({
                "file": html_file.name,
                "src": "N/A",
                "location": str(html_file.relative_to(base_dir)),
                "issue": f"Unexpected error: {str(e)}"
            })

    logger.info(f"Image validation complete: {total_images} images found, {len(image_issues)} issues")
    return {
        "total_images": total_images,
        "image_issues": image_issues
    }

def main(html_path, mode):
    """Main function to validate HTML content based on mode."""
    logger.info(f"Starting main with html_path={html_path}, mode={mode}")
    if not os.path.exists(html_path):
        error_msg = f"HTML file does not exist: {html_path}"
        logger.error(error_msg)
        print(json.dumps({"error": error_msg}, ensure_ascii=False), file=sys.stderr)
        sys.stdout.flush()
        sys.exit(1)

    if mode == "links_and_images":
        result = validate_links_and_images(html_path)
    elif mode == "internal_links":
        result = validate_internal_links(html_path, validate_html=True)
    elif mode == "images":
        result = validate_images(html_path)
    else:
        error_msg = f"Invalid mode: {mode}"
        logger.error(error_msg)
        print(json.dumps({"error": error_msg}, ensure_ascii=False), file=sys.stderr)
        sys.stdout.flush()
        sys.exit(1)

    logger.info("Outputting final result")
    print(json.dumps({"result": result}, ensure_ascii=False), file=sys.stdout)
    sys.stdout.flush()

if __name__ == "__main__":
    if len(sys.argv) != 3:
        error_msg = "Usage: python verify_html_content.py <html_path> <mode>"
        logger.error(error_msg)
        print(json.dumps({"error": error_msg}, ensure_ascii=False), file=sys.stderr)
        sys.stdout.flush()
        sys.exit(1)

    html_path = sys.argv[1]
    mode = sys.argv[2]
    main(html_path, mode)