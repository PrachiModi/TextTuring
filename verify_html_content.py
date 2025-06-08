import sys
import json
import os
from pathlib import Path
from lxml import etree
from lxml import html
import logging
from datetime import datetime
import glob
from urllib.parse import unquote
import time
import signal

# Set up logging to console only
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger(__name__)

def timeout_handler(signum, frame):
    raise TimeoutError("File processing timed out")

def validate_internal_links(html_path, validate_html=True):
    """Validate internal links in HTML or XML files within the project directory."""
    logger.info(f"Starting internal links validation for {html_path}, validate_html={validate_html}")
    total_links = 0
    link_issues = []
    base_dir = Path(html_path).parent
    topics_dir = base_dir / "Topics"
    path_cache = {}

    # Updated path mappings to preserve actual folder names
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
            [Path(html_path)] +
            list(glob.glob(str(base_dir / "**" / "*.html"), recursive=True)) +
            list(glob.glob(str(base_dir / "**" / "*.HTML"), recursive=True))
        )
        html_files = [Path(f) for f in set(html_files)]
        total_files = len(html_files)
        logger.info(f"Found {total_files} HTML files")
        print(json.dumps({"progress": f"Found {total_files} HTML files in project directory"}, ensure_ascii=False), file=sys.stderr)
        sys.stdout.flush()

        if not html_files:
            logger.warning("No HTML files found in project directory")
            print(json.dumps({"progress": "No HTML files found in project directory"}, ensure_ascii=False), file=sys.stderr)
            sys.stdout.flush()

        for idx, html_file in enumerate(html_files, 1):
            file_path = str(html_file)
            folder_name = html_file.parent.name
            logger.info(f"Processing HTML file {idx}/{total_files}: {html_file.name}")
            print(json.dumps({"progress": f"Processing HTML file {idx}/{total_files}: {file_path}"}, ensure_ascii=False), file=sys.stderr)
            sys.stdout.flush()

            try:
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(10)

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
                        # Apply path mappings
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
                            # Check for case-insensitive file existence
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

                signal.alarm(0)
                print(json.dumps({"progress": f"Completed processing {file_path}"}, ensure_ascii=False), file=sys.stderr)
                sys.stdout.flush()

            except TimeoutError:
                logger.error(f"Timeout processing {html_file.name}")
                link_issues.append({
                    "file": html_file.name,
                    "href": "N/A",
                    "location": str(html_file.relative_to(base_dir)),
                    "issue": "File processing timed out"
                })
                signal.alarm(0)
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
        xml_files = [Path(f) for f in xml_files]
        total_files = len(xml_files)
        logger.info(f"Found {total_files} XML/DITA files")
        print(json.dumps({"progress": f"Found {total_files} XML/DITA files in Topics folder"}, ensure_ascii=False), file=sys.stderr)
        sys.stdout.flush()

        if not xml_files:
            logger.warning("No XML or DITA files found in Topics folder or project root")
            print(json.dumps({"progress": "No XML or DITA files found in Topics folder or project root"}, ensure_ascii=False), file=sys.stderr)
            sys.stdout.flush()

        namespaces = {
            'dita': 'http://dita.oasis-open.org/architecture/2005/',
            '': None
        }

        for idx, xml_path in enumerate(xml_files, 1):
            file_path = str(xml_path)
            folder_name = xml_path.parent.name
            logger.info(f"Processing file {idx}/{total_files}: {xml_path.name}")
            print(json.dumps({"progress": f"Processing file {idx}/{total_files}: {file_path}"}, ensure_ascii=False), file=sys.stderr)
            sys.stdout.flush()

            try:
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(10)

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

                signal.alarm(0)
                print(json.dumps({"progress": f"Completed processing {file_path}"}, ensure_ascii=False), file=sys.stderr)
                sys.stdout.flush()

            except TimeoutError:
                logger.error(f"Timeout processing {xml_path.name}")
                link_issues.append({
                    "file": xml_path.name,
                    "href": "N/A",
                    "location": str(xml_path.relative_to(base_dir)),
                    "issue": "File processing timed out"
                })
                signal.alarm(0)
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
    print(json.dumps({"progress": f"Completed validation: {total_links} links found, {len(link_issues)} issues"}, ensure_ascii=False), file=sys.stderr)
    sys.stdout.flush()

    # Print incorrect links to console
    if link_issues:
        print("Incorrect Links:", file=sys.stderr)
        for issue in link_issues:
            print(f"File: {issue['file']}, Href: {issue['href']}, Location: {issue['location']}, Issue: {issue['issue']}", file=sys.stderr)

    return {
        "total_internal_links": total_links,
        "link_issues": link_issues
    }

def validate_images(html_path):
    """Validate images in HTML files within the project directory."""
    logger.info(f"Starting image validation for {html_path}")
    total_images = 0
    image_issues = []
    base_dir = Path(html_path).parent
    graphics_dir = base_dir / "Graphics"
    path_cache = {}

    if not graphics_dir.exists():
        error_msg = f"Graphics folder not found at {graphics_dir}"
        logger.error(error_msg)
        print(json.dumps({"error": error_msg}, ensure_ascii=False), file=sys.stderr)
        sys.stdout.flush()
        return {"error": error_msg}

    # Find all HTML files
    html_files = (
        [Path(html_path)] +
        list(glob.glob(str(base_dir / "**" / "*.html"), recursive=True)) +
        list(glob.glob(str(base_dir / "**" / "*.HTML"), recursive=True))
    )
    html_files = [Path(f) for f in set(html_files)]
    total_files = len(html_files)
    logger.info(f"Found {total_files} HTML files")
    print(json.dumps({"progress": f"Found {total_files} HTML files in project directory"}, ensure_ascii=False), file=sys.stderr)
    sys.stdout.flush()

    if not html_files:
        logger.warning("No HTML files found in project directory")
        print(json.dumps({"progress": "No HTML files found in project directory"}, ensure_ascii=False), file=sys.stderr)
        sys.stdout.flush()

    for idx, html_file in enumerate(html_files, 1):
        file_path = str(html_file)
        folder_name = html_file.parent.name
        logger.info(f"Processing HTML file {idx}/{total_files}: {html_file.name}")
        print(json.dumps({"progress": f"Processing HTML file {idx}/{total_files}: {file_path}"}, ensure_ascii=False), file=sys.stderr)
        sys.stdout.flush()

        try:
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(10)

            parser = etree.HTMLParser(recover=True)
            with open(html_file, 'rb') as f:
                tree = html.parse(f, parser=parser)
            images = tree.xpath("//img[@src]")
            total_images += len(images)
            logger.info(f"Found {len(images)} images in {html_file.name}")
            print(json.dumps({"progress": f"Found {len(images)} images in {html_file.name}"}, ensure_ascii=False), file=sys.stderr)
            sys.stdout.flush()

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

            signal.alarm(0)
            print(json.dumps({"progress": f"Completed processing {file_path}"}, ensure_ascii=False), file=sys.stderr)
            sys.stdout.flush()

        except TimeoutError:
            logger.error(f"Timeout processing {html_file.name}")
            image_issues.append({
                "file": html_file.name,
                "src": "N/A",
                "location": str(html_file.relative_to(base_dir)),
                "issue": "File processing timed out"
            })
            signal.alarm(0)
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
    print(json.dumps({"progress": f"Completed image validation: {total_images} images found, {len(image_issues)} issues"}, ensure_ascii=False), file=sys.stderr)
    sys.stdout.flush()
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

    if mode == "internal_links":
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