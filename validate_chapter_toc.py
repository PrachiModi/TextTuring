import os
import re
import logging
import xml.etree.ElementTree as ET
import urllib.parse
from pathlib import Path

# Set up logging to toc_debug.log in the DITAMAP directory
def setup_logging(ditamap_path: str):
    """Set up logging to toc_debug.log in the DITAMAP directory."""
    log_dir = os.path.dirname(ditamap_path)
    log_file = os.path.join(log_dir, "toc_debug.log")
    logger = logging.getLogger("toc_validation")
    logger.setLevel(logging.DEBUG)
    logger.handlers = []  # Clear existing handlers to avoid duplicates
    file_handler = logging.FileHandler(log_file, mode='a')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    logger.addHandler(file_handler)
    return logger

# Register DITA namespace globally
ET.register_namespace('dita', 'http://docs.oasis-open.org/dita/ns/dita')

# Global definition of intro_phrases to avoid scoping issues
intro_phrases = [
    r"this\s+chapter\s+(contains|includes|has)\s*the\s+following\s*[:\w]*",
    r"following\s+(sections|topics|commands)\s*[:\w]*",
    r"contains\s+the\s+following\s*[:\w]*",
    r"to\s+view\s+the\s+following\s*[:\w]*",
    r"click\s+on\s+a\s+client\s+.*\s+to\s+view\s+the\s+following\s*[:\w]*",
]

def validate_chapter_toc(ditamap_path: str) -> list:
    logger = setup_logging(ditamap_path)
    results = set()  # Use set for unique results
    logger.debug(f"=== Chapter TOC Validation Started: {ditamap_path} ===")

    try:
        logger.debug(f"Parsing DITA map: {ditamap_path}")
        ditamap_tree = ET.parse(ditamap_path)
        ditamap_root = ditamap_tree.getroot()
        ditamap_parent = str(Path(ditamap_path).parent)
        logger.debug(f"DITA map parent directory: {ditamap_parent}")

        chapters = ditamap_root.findall(".//chapter")
        logger.debug(f"Found {len(chapters)} <chapter> elements in DITA map")
        if not chapters:
            logger.debug("No <chapter> elements found, returning empty results")
            return list(results)

        for chapter in chapters:
            chapter_href = chapter.get('href')
            chapter_name = chapter.get('navtitle') or os.path.basename(chapter_href) if chapter_href else 'Unknown Chapter'
            logger.debug(f"Processing chapter: {chapter_name} (href: {chapter_href})")

            if not chapter_href:
                logger.debug(f"Chapter {chapter_name} has no href attribute, adding to results")
                results.add((chapter_name, "Missing href attribute", ""))
                continue

            chapter_file = urllib.parse.unquote(chapter_href).strip()
            if chapter_file.lower().endswith('.ditamap'):
                logger.debug(f"Skipping chapter {chapter_name}: href points to .ditamap file ({chapter_file})")
                continue

            chapter_xml_path = os.path.normpath(os.path.join(ditamap_parent, chapter_file))
            logger.debug(f"Resolved chapter XML path: {chapter_xml_path}")

            topicrefs = chapter.findall("./topicref")
            logger.debug(f"Found {len(topicrefs)} first-level <topicref> elements in chapter {chapter_name}")
            if len(topicrefs) == 0:
                logger.debug(f"Skipping chapter {chapter_name}: No topicrefs found")
                continue
            if len(topicrefs) == 1:
                logger.debug(f"Skipping chapter {chapter_name}: Only one topicref, no TOC needed")
                continue

            topicref_hrefs = {
                os.path.basename(urllib.parse.unquote(tr.get('href')).strip()).lower(): tr.get('href')
                for tr in topicrefs if tr.get('href') and not urllib.parse.unquote(tr.get('href')).strip().lower().endswith('.ditamap')
            }
            logger.debug(f"Collected topicrefs: {list(topicref_hrefs.keys())}")
            if not topicref_hrefs:
                logger.debug(f"No valid first-level topicrefs found for chapter {chapter_name}, adding to results")
                results.add((chapter_name, "No first-level topicrefs found", chapter_xml_path))
                continue

            try:
                logger.debug(f"Parsing chapter XML: {chapter_xml_path}")
                xml_tree = ET.parse(chapter_xml_path)
                xml_root = xml_tree.getroot()
                logger.debug(f"Successfully parsed chapter XML: {chapter_xml_path}")
            except ET.ParseError as e:
                logger.debug(f"Chapter {chapter_name}: XML parsing error ({str(e)}), adding to results")
                results.add((chapter_name, f"Chapter XML parsing error: {str(e)}", chapter_xml_path))
                continue
            except FileNotFoundError:
                logger.debug(f"Chapter {chapter_name}: XML file not found, adding to results")
                results.add((chapter_name, "Chapter XML not found", chapter_xml_path))
                continue

            ul_xref_hrefs = set()
            has_ul = False
            for ul in xml_root.findall(".//ul"):
                has_ul = True
                for li in ul.findall("./li"):
                    xref = li.find(".//xref")
                    if xref is not None and xref.get('href'):
                        href = urllib.parse.unquote(xref.get('href')).strip().split('#')[0]
                        ul_xref_hrefs.add(os.path.basename(href).lower())
                logger.debug(f"Found <ul> with {len(ul_xref_hrefs)} <xref> hrefs: {ul_xref_hrefs}")

            all_xref_hrefs = set(ul_xref_hrefs)
            standalone_xrefs = xml_root.findall(".//xref[@href]")
            logger.debug(f"Found {len(standalone_xrefs)} standalone <xref> elements")
            for xref in standalone_xrefs:
                href = urllib.parse.unquote(xref.get('href')).strip().split('#')[0]
                all_xref_hrefs.add(os.path.basename(href).lower())
            logger.debug(f"All <xref> hrefs in chapter XML: {all_xref_hrefs}")

            unmatched_topics = {k: v for k, v in topicref_hrefs.items() if k not in all_xref_hrefs}
            logger.debug(f"Unmatched topicrefs (missing from <xref>s): {unmatched_topics}")

            if not has_ul and not unmatched_topics:
                logger.debug(f"Chapter {chapter_name}: No <ul> but all topicrefs matched, skipping")
                continue

            if unmatched_topics:
                logger.debug(f"Chapter {chapter_name}: Found {len(unmatched_topics)} missing topics")
                for topic_file, topic_href in unmatched_topics.items():
                    topic_path = os.path.normpath(os.path.join(ditamap_parent, topic_href))
                    logger.debug(f"Processing missing topic: {topic_file} (path: {topic_path})")
                    try:
                        topic_tree = ET.parse(topic_path)
                        title_elem = topic_tree.find(".//title")
                        topic_title = title_elem.text.strip() if title_elem is not None and title_elem.text else topic_file
                        logger.debug(f"Adding result: Missing topic '{topic_title}' in chapter {chapter_name}")
                        results.add((chapter_name, f"Missing: {topic_title}", chapter_xml_path))
                    except FileNotFoundError:
                        logger.debug(f"Topic {topic_file}: XML file not found, adding to results")
                        results.add((chapter_name, f"Missing: {topic_file} (Topic XML not found)", chapter_xml_path))
                    except ET.ParseError:
                        logger.debug(f"Topic {topic_file}: XML parsing error, adding to results")
                        results.add((chapter_name, f"Missing: {topic_file} (Topic XML parsing error)", chapter_xml_path))

        logger.debug(f"=== Chapter TOC Validation Complete ===\nIssues found: {len(results)}")
        for result in results:
            logger.debug(f"Result: Chapter={result[0]}, Issue={result[1]}, XML Path={result[2]}")
        if not results:
            logger.debug("No chapter TOC issues found")
        return list(results)

    except ET.ParseError as e:
        logger.debug(f"Error parsing DITA map file {ditamap_path}: {str(e)}")
        results.add(("Error", f"DITA map parsing error: {str(e)}", ditamap_path))
        return list(results)
    except FileNotFoundError:
        logger.debug(f"DITA map file not found: {ditamap_path}")
        results.add(("Error", "DITA map not found", ditamap_path))
        return list(results)
    except Exception as e:
        logger.debug(f"Unexpected error in DITA map: {ditamap_path}: {str(e)}")
        results.add(("Error", f"Unexpected error: {str(e)}", ditamap_path))
        return list(results)

def validate_subchapter_toc(ditamap_path: str) -> list:
    """
    Validate that all immediate nested topicrefs in a DITA map's parent topicrefs are listed as xrefs
    in the corresponding XML's <ul> lists. Recursively validate child topics with nested content.
    Only check for missing subtopics, ignoring extraneous <xref>s. Skip <xref>s within <table> elements.
    Relax intro phrase check for topics with 'Commands' in the title.
    """
    logger = setup_logging(ditamap_path)
    results = set()  # Use set for unique results
    logger.debug(f"=== Subchapter TOC Validation Started: {ditamap_path} ===")

    def get_immediate_topicrefs(topicref):
        """Collect only immediate <topicref> children with href attributes."""
        topicrefs = [tr for tr in topicref.findall("./topicref") if tr.get('href') and not urllib.parse.unquote(tr.get('href')).strip().lower().endswith('.ditamap')]
        logger.debug(f"get_immediate_topicrefs: Found {len(topicrefs)} topicrefs")
        return topicrefs

    def validate_topic(parent_topicref, ditamap_parent):
        parent_href = parent_topicref.get('href')
        if not parent_href:
            logger.debug("Skipping parent topic: No href attribute")
            return

        parent_file = urllib.parse.unquote(parent_href).strip()
        if parent_file.lower().endswith('.ditamap'):
            logger.debug(f"Skipping parent topic: href points to .ditamap file ({parent_file})")
            return

        parent_xml_path = os.path.normpath(os.path.join(ditamap_parent, parent_file))
        parent_name = parent_topicref.get('navtitle') or os.path.splitext(os.path.basename(parent_file))[0]
        logger.debug(f"=== Processing Parent Topic: {parent_name} ===\nXML path: {parent_xml_path}")

        logger.debug(f"{parent_name.upper()} PROCESSING STARTED: path={parent_xml_path}")

        try:
            logger.debug(f"Parsing parent XML: {parent_xml_path}")
            xml_tree = ET.parse(parent_xml_path)
            xml_root = xml_tree.getroot()
            logger.debug(f"{parent_name.upper()}: Successfully parsed XML")
        except ET.ParseError as e:
            logger.debug(f"{parent_name.upper()}: Failed to parse XML: {str(e)}")
            return
        except FileNotFoundError:
            logger.debug(f"{parent_name.upper()}: XML file not found")
            return

        conbody = xml_root.find(".//conbody")
        if conbody is None:
            logger.debug(f"{parent_name.upper()}: No <conbody> found, skipping")
            return

        logger.debug(f"{parent_name.upper()}: Found <conbody>")

        has_valid_ul = False
        valid_ul = None
        ul_elements = []
        ul_elements.extend(conbody.findall(".//ul"))
        for section in conbody.findall(".//section"):
            ul_elements.extend(section.findall(".//ul"))
        logger.debug(f"{parent_name.upper()}: Found {len(ul_elements)} <ul> elements")

        for ul in ul_elements:
            li_elements = ul.findall("./li")
            xref_count = 0
            for li in li_elements:
                xref = li.find(".//xref[@href]")
                if xref is not None and xref.get('href'):
                    parent = li
                    is_in_table = False
                    while parent is not None:
                        if parent.tag == 'table':
                            is_in_table = True
                            break
                        parent = parent.find('..')
                    if not is_in_table:
                        xref_count += 1
            logger.debug(f"{parent_name.upper()}: Checking <ul id={ul.get('id')}>, xref_count={xref_count}")
            if xref_count >= 2:
                valid_ul = ul
                has_valid_ul = True
                parent_p = None
                for p in conbody.findall(".//p"):
                    if ul in p.findall(".//ul"):
                        parent_p = p
                        break
                if parent_p is None:
                    for s in conbody.findall(".//section"):
                        if ul in s.findall(".//ul"):
                            break
                logger.debug(f"{parent_name.upper()}: Valid <ul> found, id={ul.get('id')}, parent_p={'Yes' if parent_p is not None else 'No'}")
                break

        if not has_valid_ul:
            logger.debug(f"{parent_name.upper()}: No <ul> with multiple <xref>s found, skipping")
            return

        if parent_p is not None and valid_ul is not None:
            non_ul_content = []
            for child in parent_p:
                if child.tag != 'ul':
                    non_ul_content.append(''.join(child.itertext()).strip())
                elif child != valid_ul:
                    non_ul_content.append(''.join(child.itertext()).strip())
            for text in parent_p.itertext():
                if text.strip():
                    non_ul_content.append(text.strip())
            non_ul_content = [c for c in non_ul_content if c]
            inline_text = ' '.join(non_ul_content)
            is_intro = any(re.search(phrase, inline_text.lower()) for phrase in intro_phrases)
            inline_length = len(inline_text) if not is_intro else 0
            li_inline_content = []
            for li in valid_ul.findall("./li"):
                xref = li.find(".//xref[@href]")
                if xref is None:
                    li_inline_content.append(''.join(li.itertext()).strip())
            li_inline_length = len(' '.join([c for c in li_inline_content if c]))
            elements = parent_p.findall(".//*")
            element_tags = [elem.tag for elem in elements]
            logger.debug(f"{parent_name.upper()}: Heuristic check: inline_length={inline_length}, elements_in_p={len(elements)}, element_tags={element_tags}, li_inline_length={li_inline_length}, ul_id={valid_ul.get('id')}")
            if inline_length > 100 or len(elements) > 20 or li_inline_length > 100:
                logger.debug(f"{parent_name.upper()}: Skipped due to heuristic failure: inline_length={inline_length}, elements_in_p={len(elements)}, li_inline_length={li_inline_length}")
                return

        is_command_topic = "Commands" in parent_name
        has_intro_or_colon = is_command_topic or False
        if not is_command_topic:
            for p in conbody.findall(".//p"):
                text = ''.join(p.itertext()).strip().lower()
                logger.debug(f"{parent_name.upper()}: Checking intro phrase: {text}")
                if valid_ul in p.findall(".//ul"):
                    if re.search(r".*:[\s]*$", text):
                        has_intro_or_colon = True
                        logger.debug(f"{parent_name.upper()}: Found colon-ending intro phrase")
                        break
                if any(re.search(phrase, text) for phrase in intro_phrases):
                    has_intro_or_colon = True
                    logger.debug(f"{parent_name.upper()}: Found matching intro phrase: {text}")
                    break

        if not has_intro_or_colon:
            logger.debug(f"{parent_name.upper()}: No introductory phrase or colon found, skipping")
            return

        logger.debug(f"{parent_name.upper()}: Mini-TOC candidate validated")

        immediate_topicrefs = get_immediate_topicrefs(parent_topicref)
        logger.debug(f"{parent_name.upper()}: Found {len(immediate_topicrefs)} immediate nested topicrefs")
        if len(immediate_topicrefs) <= 1:
            logger.debug(f"{parent_name.upper()}: Skipped due to zero or one immediate nested topicref")
            return

        topicref_hrefs = {
            os.path.basename(urllib.parse.unquote(tr.get('href')).strip()): urllib.parse.unquote(tr.get('href')).strip()
            for tr in immediate_topicrefs if tr.get('href')
        }
        logger.debug(f"{parent_name.upper()}: Expected subtopics (from DITA map immediate <topicref>s): {list(topicref_hrefs.keys())}")

        if not topicref_hrefs:
            logger.debug(f"{parent_name.upper()}: No immediate nested topicrefs found, skipping")
            return

        xref_hrefs = set()
        for ul in ul_elements:
            for li in ul.findall("./li"):
                xref = li.find(".//xref[@href]")
                if xref is not None and xref.get('href'):
                    parent = li
                    is_in_table = False
                    while parent is not None:
                        if parent.tag == 'table':
                            is_in_table = True
                            break
                        parent = parent.find('..')
                    if not is_in_table:
                        href = urllib.parse.unquote(xref.get('href')).strip().split('#')[0]
                        xref_hrefs.add(os.path.basename(href))
        logger.debug(f"{parent_name.upper()}: Found subtopics (from XML <xref>s): {list(xref_hrefs)}")

        missing_hrefs = [href for href in topicref_hrefs if os.path.basename(href) not in xref_hrefs]
        logger.debug(f"{parent_name.upper()}: Missing subtopics: {missing_hrefs}")

        if missing_hrefs:
            logger.debug(f"{parent_name.upper()}: Issues in subtopics:")
            for href in missing_hrefs:
                logger.debug(f"- Missing: {os.path.basename(href)}: Not found in xref_hrefs {list(xref_hrefs)}")

        for href in missing_hrefs:
            full_href = topicref_hrefs[href]
            topic_path = os.path.normpath(os.path.join(ditamap_parent, full_href))
            logger.debug(f"{parent_name.upper()}: Fetching title for missing subtopic: {topic_path}")
            try:
                topic_tree = ET.parse(topic_path)
                title_elem = topic_tree.find(".//title")
                subtopic_title = title_elem.text.strip() if title_elem is not None and title_elem.text else os.path.basename(href)
                issue = (parent_name, f"Missing: {subtopic_title}", parent_xml_path, topic_path)
                results.add(issue)
                logger.debug(f"{parent_name.upper()}: Adding result: Missing Subtopic: Chapter={parent_name}, Subtopic={subtopic_title}, XML={parent_xml_path}")
            except FileNotFoundError:
                logger.debug(f"{parent_name.upper()}: Missing Subtopic: Chapter={parent_name}, Subtopic={href} (Topic XML not found), XML={parent_xml_path}")
                results.add((parent_name, f"Missing: {href} (Topic XML not found)", parent_xml_path, topic_path))
            except ET.ParseError:
                logger.debug(f"{parent_name.upper()}: Missing Subtopic: Chapter={parent_name}, Subtopic={href} (Topic XML parsing error), XML={parent_xml_path}")
                results.add((parent_name, f"Missing: {href} (Topic XML parsing error)", parent_xml_path, topic_path))

        for child_topicref in immediate_topicrefs:
            if get_immediate_topicrefs(child_topicref):
                logger.debug(f"{parent_name.upper()}: Recursively validating child topicref")
                validate_topic(child_topicref, ditamap_parent)

    try:
        logger.debug(f"Parsing DITA map for subchapter validation: {ditamap_path}")
        ditamap_tree = ET.parse(ditamap_path)
        ditamap_root = ditamap_tree.getroot()
        ditamap_parent = str(Path(ditamap_path).parent)
        logger.debug(f"DITA map parent directory: {ditamap_parent}")

        parent_topicrefs = []
        for topicref in ditamap_root.iter("topicref"):
            if topicref.get('href') and get_immediate_topicrefs(topicref):
                parent_topicrefs.append(topicref)
        logger.debug(f"Found {len(parent_topicrefs)} parent topicrefs with immediate nested topicrefs")

        for parent_topicref in parent_topicrefs:
            validate_topic(parent_topicref, ditamap_parent)

        logger.debug(f"=== Subchapter TOC Validation Complete ===\nIssues found: {len(results)}")
        for result in results:
            logger.debug(f"Result: Chapter={result[0]}, Issue={result[1]}, Parent XML={result[2]}, Subtopic Path={result[3]}")
        if not results:
            logger.debug("No subchapter TOC issues found")
        return list(results)

    except ET.ParseError as e:
        logger.debug(f"Error parsing DITA map file {ditamap_path}: {str(e)}")
        results.add(("Error", f"DITA map parsing error: {str(e)}", ditamap_path, ""))
        return list(results)
    except FileNotFoundError:
        logger.debug(f"DITA map file not found: {ditamap_path}")
        results.add(("Error", "DITA map not found", ditamap_path, ""))
        return list(results)
    except Exception as e:
        logger.debug(f"Unexpected error in DITA map: {ditamap_path}: {str(e)}")
        results.add(("Error", f"Unexpected error: {str(e)}", ditamap_path, ""))
        return list(results)

def get_immediate_topicrefs(topicref):
    """Collect only immediate <topicref> children with href attributes."""
    topicrefs = [tr for tr in topicref.findall("./topicref") if tr.get('href') and not urllib.parse.unquote(tr.get('href')).strip().lower().endswith('.ditamap')]
    logger.debug(f"get_immediate_topicrefs: Found {len(topicrefs)} topicrefs")
    return topicrefs