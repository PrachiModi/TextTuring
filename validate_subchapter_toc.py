import os
import xml.etree.ElementTree as ET
import urllib.parse
from pathlib import Path
import logging

# Set up logging to console only
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

def validate_chapter_toc(ditamap_path: str) -> list:
    """
    Validate that all first-level topicrefs in a DITA map's chapters are listed in the
    corresponding chapter XML's <ul> list. Only report missing topics, not extra xrefs.

    Args:
        ditamap_path: Path to the DITA map file.

    Returns:
        list: List of tuples (chapter_name, topic_name, chapter_xml_path) for each issue.
              - chapter_name: Chapter navtitle or file name.
              - topic_name: Missing topic title or file name (e.g., "Missing: <title>").
              - chapter_xml_path: Path to the chapter XML file.
    """
    results = []
    logger = logging.getLogger(__name__)
    logger.debug(f"Starting validation for DITA map: {ditamap_path}")

    try:
        # Parse the DITA map file
        ditamap_tree = ET.parse(ditamap_path)
        ditamap_root = ditamap_tree.getroot()
        ditamap_parent = str(Path(ditamap_path).parent)
        logger.debug(f"DITA map parent dir: {ditamap_parent}")

        # Find all chapter elements
        chapters = ditamap_root.findall(".//chapter")
        logger.debug(f"Found {len(chapters)} chapters")
        if not chapters:
            logger.debug("No <chapter> elements found in the DITA map.")
            return results

        for chapter in chapters:
            # Get the chapter's href and navtitle
            chapter_href = chapter.get('href')
            chapter_name = chapter.get('navtitle') or os.path.basename(chapter_href) if chapter_href else 'Unknown Chapter'
            logger.debug(f"\n=== Chapter: {chapter_name} ===")

            if not chapter_href:
                logger.debug("Chapter missing href attribute.")
                results.append((chapter_name, "Missing href attribute", ""))
                continue

            # Decode URL-encoded characters and normalize path
            chapter_file = urllib.parse.unquote(chapter_href).strip()
            chapter_xml_path = os.path.normpath(os.path.join(ditamap_parent, chapter_file))
            logger.debug(f"Chapter href: {chapter_href}, XML path: {chapter_xml_path}")

            # Get all first-level topicref hrefs and extract basenames
            topicrefs = chapter.findall("./topicref")
            topicref_hrefs = {
                os.path.basename(urllib.parse.unquote(tr.get('href')).strip()): tr.get('href')
                for tr in topicrefs if tr.get('href')
            }
            logger.debug(f"Expected topics: {list(topicref_hrefs.keys())}")
            logger.debug(f"Expected raw hrefs: {list(topicref_hrefs.values())}")
            if not topicref_hrefs:
                logger.debug(f"No first-level <topicref> elements found in chapter.")
                results.append((chapter_name, "No first-level topicrefs found", chapter_xml_path))
                continue

            # Parse the chapter's XML file
            try:
                xml_tree = ET.parse(chapter_xml_path)
                xml_root = xml_tree.getroot()
            except ET.ParseError as e:
                logger.debug(f"Error parsing chapter XML file {chapter_xml_path}: {e}")
                results.append((chapter_name, f"Chapter XML parsing error: {str(e)}", chapter_xml_path))
                continue
            except FileNotFoundError:
                logger.debug(f"Chapter XML file not found: {chapter_xml_path}")
                results.append((chapter_name, "Chapter XML not found", chapter_xml_path))
                continue

            # Find all <xref> elements within <li> tags in the <ul>
            xref_hrefs = []
            has_ul = False
            for ul in xml_root.findall(".//ul"):
                has_ul = True
                for li in ul.findall("./li"):
                    xref = li.find(".//xref")
                    if xref is not None and xref.get('href'):
                        xref_hrefs.append(os.path.basename(urllib.parse.unquote(xref.get('href')).strip()))

            logger.debug(f"TOC status: {'Present' if xref_hrefs else 'Empty' if has_ul else 'Missing'}")
            logger.debug(f"Listed topics in TOC: {xref_hrefs}")
            logger.debug(f"Listed raw hrefs: {[urllib.parse.unquote(x.get('href')).strip() for x in xml_root.findall('.//ul/li//xref[@href]')]}")

            # Handle missing or empty <ul>
            if not has_ul or not xref_hrefs:
                status = "Missing" if not has_ul else "Empty"
                logger.debug(f"{status} <ul> detected in {chapter_xml_path}")
                for topic_file, topic_href in topicref_hrefs.items():
                    topic_path = os.path.normpath(os.path.join(ditamap_parent, topic_href))
                    logger.debug(f"Fetching title for topic: {topic_path}")
                    try:
                        topic_tree = ET.parse(topic_path)
                        title_elem = topic_tree.find(".//title")
                        topic_title = title_elem.text.strip() if title_elem is not None and title_elem.text else topic_file
                        results.append((chapter_name, f"Missing: {topic_title}", chapter_xml_path))
                        logger.debug(f"Added missing topic: {topic_title}")
                    except FileNotFoundError:
                        results.append((chapter_name, f"Missing: {topic_file} (Topic XML not found)", chapter_xml_path))
                        logger.debug(f"Topic XML not found: {topic_file}")
                    except ET.ParseError as e:
                        results.append((chapter_name, f"Missing: {topic_file} (Topic XML parsing error: {str(e)})", chapter_xml_path))
                        logger.debug(f"Topic XML parsing error: {topic_file}")
                    except Exception as e:
                        results.append((chapter_name, f"Missing: {topic_file} (Error: {str(e)})", chapter_xml_path))
                        logger.debug(f"Topic XML error: {topic_file}, {str(e)}")
                continue

            # Compare topicref href basenames with xref hrefs (only check for missing)
            missing_hrefs = [href for href in topicref_hrefs if href not in xref_hrefs]
            logger.debug(f"Missing topics: {missing_hrefs}")
            for href in missing_hrefs:
                topic_path = os.path.normpath(os.path.join(ditamap_parent, topicref_hrefs[href]))
                logger.debug(f"Fetching title for missing topic: {topic_path}")
                try:
                    topic_tree = ET.parse(topic_path)
                    title_elem = topic_tree.find(".//title")
                    topic_title = title_elem.text.strip() if title_elem is not None and title_elem.text else href
                    results.append((chapter_name, f"Missing: {topic_title}", chapter_xml_path))
                    logger.debug(f"Added missing topic: {topic_title}")
                except FileNotFoundError:
                    results.append((chapter_name, f"Missing: {href} (Topic XML not found)", chapter_xml_path))
                    logger.debug(f"Topic XML not found: {href}")
                except ET.ParseError as e:
                    results.append((chapter_name, f"Missing: {href} (Topic XML parsing error: {str(e)})", chapter_xml_path))
                    logger.debug(f"Topic XML parsing error: {href}")
                except Exception as e:
                    results.append((chapter_name, f"Missing: {href} (Error: {str(e)})", chapter_xml_path))
                    logger.debug(f"Topic XML error: {href}, {str(e)}")

        logger.debug(f"\nValidation complete, issues found: {len(results)}")
        return results

    except ET.ParseError as e:
        logger.error(f"Error parsing DITA map file {ditamap_path}: {e}")
        return [("Error", f"DITA map parsing error: {str(e)}", ditamap_path)]
    except FileNotFoundError:
        logger.error(f"DITA map file not found: {ditamap_path}")
        return [("Error", "DITA map not found", ditamap_path)]
    except Exception as e:
        logger.error(f"Unexpected error in DITA map: {ditamap_path}, {str(e)}")
        return [("Error", f"Unexpected error: {str(e)}", ditamap_path)]

def validate_subchapter_toc(ditamap_path: str) -> list:
    """
    Validate that all nested topicrefs in a DITA map's parent topicrefs are listed as xrefs
    in the corresponding XML's <ul> lists. Only process XMLs with bulleted lists of xrefs.
    Prints results to console.

    Args:
        ditamap_path: Path to the DITA map file.

    Returns:
        list: List of tuples (chapter_name, subtopic_name, chapter_xml_path) for each issue.
    """
    results = []
    logger = logging.getLogger(__name__)
    logger.debug(f"Starting subchapter TOC validation for DITA map: {ditamap_path}")

    try:
        # Parse the DITA map file
        ditamap_tree = ET.parse(ditamap_path)
        ditamap_root = ditamap_tree.getroot()
        ditamap_parent = str(Path(ditamap_path).parent)
        logger.debug(f"DITA map parent dir: {ditamap_parent}")

        # Find all parent topicrefs with nested topicrefs
        parent_topicrefs = ditamap_root.findall(".//topicref[topicref]")
        logger.debug(f"Found {len(parent_topicrefs)} parent topicrefs with nested topicrefs")

        for parent_topicref in parent_topicrefs:
            parent_href = parent_topicref.get('href')
            if not parent_href:
                logger.debug("Parent topicref missing href attribute")
                continue

            # Decode and normalize parent href
            parent_file = urllib.parse.unquote(parent_href).strip()
            parent_xml_path = os.path.normpath(os.path.join(ditamap_parent, parent_file))
            parent_name = parent_topicref.get('navtitle') or os.path.splitext(os.path.basename(parent_file))[0]
            logger.debug(f"\n=== Parent Topic: {parent_name} ===, XML path: {parent_xml_path}")

            # Parse the parent XML to check for bulleted lists
            try:
                xml_tree = ET.parse(parent_xml_path)
                xml_root = xml_tree.getroot()
            except ET.ParseError as e:
                logger.debug(f"Error parsing parent XML file {parent_xml_path}: {e}")
                continue
            except FileNotFoundError:
                logger.debug(f"Parent XML file not found: {parent_xml_path}")
                continue

            # Check for <ul> with <xref> in <li>
            has_bulleted_list = False
            for ul in xml_root.findall(".//ul"):
                for li in ul.findall("./li"):
                    xref = li.find(".//xref")
                    if xref is not None and xref.get('href'):
                        has_bulleted_list = True
                        break
                if has_bulleted_list:
                    break

            if not has_bulleted_list:
                logger.debug(f"No bulleted lists with xrefs found in {parent_xml_path}")
                continue

            # Get nested topicref hrefs
            nested_topicrefs = parent_topicref.findall("./topicref")
            topicref_hrefs = {
                os.path.basename(urllib.parse.unquote(tr.get('href')).strip()): tr.get('href')
                for tr in nested_topicrefs if tr.get('href')
            }
            logger.debug(f"Expected subtopics: {list(topicref_hrefs.keys())}")

            if not topicref_hrefs:
                logger.debug(f"No nested topicrefs found in parent topicref")
                continue

            # Get xref hrefs from XML
            xref_hrefs = []
            for ul in xml_root.findall(".//ul"):
                for li in ul.findall("./li"):
                    xref = li.find(".//xref")
                    if xref is not None and xref.get('href'):
                        href = urllib.parse.unquote(xref.get('href')).strip()
                        xref_hrefs.append(os.path.basename(href))

            logger.debug(f"Listed subtopics in XML: {xref_hrefs}")

            # Find missing subtopics
            missing_hrefs = [href for href in topicref_hrefs if href not in xref_hrefs]
            logger.debug(f"Missing subtopics: {missing_hrefs}")

            for href in missing_hrefs:
                topic_path = os.path.normpath(os.path.join(ditamap_parent, topicref_hrefs[href]))
                logger.debug(f"Fetching title for missing subtopic: {topic_path}")
                try:
                    topic_tree = ET.parse(topic_path)
                    title_elem = topic_tree.find(".//title")
                    subtopic_title = title_elem.text.strip() if title_elem is not None and title_elem.text else href
                    issue = (parent_name, f"Missing: {subtopic_title}", parent_xml_path)
                    results.append(issue)
                    # Print to console
                    print(f"Missing Subtopic: Chapter={parent_name}, Subtopic={subtopic_title}, XML={parent_xml_path}")
                    logger.debug(f"Added missing subtopic: {subtopic_title}")
                except FileNotFoundError:
                    issue = (parent_name, f"Missing: {href} (Topic XML not found)", parent_xml_path)
                    results.append(issue)
                    print(f"Missing Subtopic: Chapter={parent_name}, Subtopic={href} (Topic XML not found), XML={parent_xml_path}")
                    logger.debug(f"Topic XML not found: {href}")
                except ET.ParseError as e:
                    issue = (parent_name, f"Missing: {href} (Topic XML parsing error: {str(e)})", parent_xml_path)
                    results.append(issue)
                    print(f"Missing Subtopic: Chapter={parent_name}, Subtopic={href} (Topic XML parsing error: {str(e)}), XML={parent_xml_path}")
                    logger.debug(f"Topic XML parsing error: {href}")
                except Exception as e:
                    issue = (parent_name, f"Missing: {href} (Error: {str(e)})", parent_xml_path)
                    results.append(issue)
                    print(f"Missing Subtopic: Chapter={parent_name}, Subtopic={href} (Error: {str(e)}), XML={parent_xml_path}")
                    logger.debug(f"Topic XML error: {href}, {str(e)}")

        logger.debug(f"\nSubchapter TOC validation complete, issues found: {len(results)}")
        if not results:
            print("No subchapter TOC issues found")
        return results

    except ET.ParseError as e:
        logger.error(f"Error parsing DITA map file {ditamap_path}: {e}")
        print(f"Error: DITA map parsing error: {str(e)}")
        return [("Error", f"DITA map parsing error: {str(e)}", ditamap_path)]
    except FileNotFoundError:
        logger.error(f"DITA map file not found: {ditamap_path}")
        print("Error: DITA map not found")
        return [("Error", "DITA map not found", ditamap_path)]
    except Exception as e:
        logger.error(f"Unexpected error in DITA map: {ditamap_path}, {str(e)}")
        print(f"Error: Unexpected error: {str(e)}")
        return [("Error", f"Unexpected error: {str(e)}", ditamap_path)]