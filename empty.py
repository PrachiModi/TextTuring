import sys
import os
import shutil
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QFileDialog
from lxml import etree
from urllib.parse import unquote
import uuid
import logging

# Set up logging for LegacyTextTuring/Log.txt in the parent directory of the ditamap
def setup_logging(ditamap_dir):
    """Set up logging to LegacyTextTuring/Log.txt in the parent directory of the ditamap."""
    parent_dir = os.path.dirname(ditamap_dir)
    legacy_dir = os.path.join(parent_dir, "LegacyTextTuring")
    os.makedirs(legacy_dir, exist_ok=True)
    log_file = os.path.join(legacy_dir, "Log.txt")
    logger = logging.getLogger("empty_xml_logger")
    logger.setLevel(logging.INFO)
    logger.handlers = []  # Clear existing handlers to avoid duplicates
    file_handler = logging.FileHandler(log_file, mode='a')
    file_handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(file_handler)
    return logger

def backup_file(xml_path, ditamap_dir):
    """
    Copy the original XML file to LegacyTextTuring, preserving the relative directory structure.
    Returns True if copied or no copy needed, False if error.
    """
    try:
        parent_dir = os.path.dirname(ditamap_dir)
        legacy_base_dir = os.path.join(parent_dir, "LegacyTextTuring")
        relative_path = os.path.relpath(xml_path, parent_dir)
        legacy_path = os.path.join(legacy_base_dir, relative_path)
        os.makedirs(os.path.dirname(legacy_path), exist_ok=True)
        if os.path.exists(legacy_path):
            logging.debug(f"Backup skipped: {legacy_path} already exists")
            return True
        shutil.copy2(xml_path, legacy_path)
        logging.debug(f"Backed up {xml_path} to {legacy_path}")
        return True
    except OSError as e:
        logging.error(f"Failed to back up {xml_path} to {legacy_path}: {str(e)}")
        return False

def is_empty_except_title(xml_path):
    """Check if an XML file contains only a title element and no other significant content."""
    try:
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(str(xml_path), parser)
        root = tree.getroot()
        
        children = [child for child in root if etree.iselement(child)]
        title_elements = root.xpath("//title")
        
        has_title = len(title_elements) == 1
        has_other_content = False
        
        for child in children:
            if child.tag not in {"title", "conbody", "body"}:
                if child.text and child.text.strip():
                    has_other_content = True
                    break
                if child.tail and child.tail.strip():
                    has_other_content = True
                    break
                if len(child) > 0:
                    has_other_content = True
                    break
            elif child.tag in {"conbody", "body"}:
                if child.text and child.text.strip():
                    has_other_content = True
                    break
                if child.tail and child.tail.strip():
                    has_other_content = True
                    break
                if len(child) > 0:
                    has_other_content = True
                    break
        
        return has_title and not has_other_content
    except etree.LxmlError:
        return False
    except Exception:
        return False

def serialize_element(elem, level=0, indent="  "):
    """Serialize an XML element to a string with consistent 2-space indentation."""
    result = []
    attrs = []
    for k, v in sorted(elem.items()):
        if k == "{http://www.w3.org/XML/1998/namespace}lang":
            attrs.append(f'xml:lang="{v}"')
        else:
            attrs.append(f'{k}="{v}"')
    attrs_str = ' '.join(attrs)
    
    # Handle self-closing tags for xref with no text or children
    if elem.tag == "xref" and not elem.text and not len(elem):
        result.append(f"{' ' * level * len(indent)}<{elem.tag}{' ' + attrs_str if attrs_str else ''}/>")
        return result
    
    # Opening tag
    tag_line = f"{' ' * level * len(indent)}<{elem.tag}{' ' + attrs_str if attrs_str else ''}>"
    result.append(tag_line)
    
    # Process text content
    if elem.text and elem.text.strip():
        text = elem.text.strip()
        if elem.tag in {"title", "p"}:
            result[-1] = f"{' ' * level * len(indent)}<{elem.tag}{' ' + attrs_str if attrs_str else ''}>{text}"
        else:
            result.append(f"{' ' * (level + 1) * len(indent)}{text}")
    
    # Process child elements
    for child in elem:
        result.extend(serialize_element(child, level + 1, indent))
    
    # Closing tag
    if len(elem) > 0 or (elem.text and elem.text.strip()):
        result.append(f"{' ' * level * len(indent)}</{elem.tag}>")
    
    return result

def update_xml_file(xml_path, child_hrefs, ditamap_dir):
    """
    Update an XML file with a body or conbody containing xrefs to child hrefs.
    Modify the root ID by appending ttu_[original_id].
    Backup the original file to LegacyTextTuring before updating.
    Log the update to LegacyTextTuring/Log.txt in the parent directory.
    """
    logger = setup_logging(ditamap_dir)
    
    if not backup_file(xml_path, ditamap_dir):
        return False
    
    try:
        parser = etree.XMLParser(recover=True, remove_blank_text=True)
        tree = etree.parse(str(xml_path), parser)
        root = tree.getroot()
        
        title = root.find("title")
        if title is None:
            logger.error(f"No title found in {xml_path}")
            return False
        
        # Modify the root ID
        orig_id = root.get('id')
        if orig_id:
            new_id = f"ttu_{orig_id}"
            root.set('id', new_id)
            logger.debug(f"Updated ID from {orig_id} to {new_id} in {xml_path}")
        
        doctype = tree.docinfo.doctype
        body_tag = "body" if "topic.dtd" in doctype else "conbody"
        
        for elem in root.findall("body") + root.findall("conbody"):
            root.remove(elem)
        
        body_elem = etree.Element(body_tag)
        p = etree.Element("p")
        p.text = "This chapter has the following sections:"
        ul = etree.Element("ul", id=f"ul_{uuid.uuid4().hex[:12]}")
        
        logger.debug(f"Processing child_hrefs: {child_hrefs}")
        base_dir = Path(ditamap_dir)
        for href in child_hrefs:
            logger.debug(f"Handling href: {href}")
            li = etree.Element("li")
            xref_href = href.split('/')[-1]
            xref = etree.Element("xref", href=xref_href)
            li.append(xref)
            ul.append(li)
        
        p.append(ul)
        body_elem.append(p)
        root.append(body_elem)
        
        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            doctype,
            *serialize_element(root, indent="  ")
        ]
        
        with open(xml_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(xml_lines) + '\n')
        
        relative_path = os.path.relpath(xml_path, os.path.dirname(ditamap_dir))
        logger.info(f"{relative_path} - Populated child toc and updated ID.\n")
        
        return True
    except etree.LxmlError as e:
        logger.error(f"XML parsing error in {xml_path}: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Error updating {xml_path}: {str(e)}")
        return False

def process_ditamap(ditamap_path):
    """Process a DITAMAP file and update empty XML files."""
    base_dir = Path(ditamap_path).parent
    ditamap_dir = str(base_dir)
    
    try:
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(str(ditamap_path), parser)
        namespaces = {'dita': 'http://dita.oasis-open.org/architecture/2005/'}
        
        topicrefs = tree.xpath("//dita:topicref | //topicref | //dita:chapter | //chapter", namespaces=namespaces)
        
        for topicref in topicrefs:
            href = topicref.get("href")
            if not href:
                continue
            
            decoded_href = unquote(href)
            try:
                xml_path = (base_dir / decoded_href).resolve()
                if not xml_path.exists():
                    continue
                if xml_path.suffix.lower() not in ('.xml', '.dita'):
                    continue
                
                child_hrefs = [child.get("href") for child in topicref.xpath("./dita:topicref | ./topicref", namespaces=namespaces) if child.get("href")]
                
                if is_empty_except_title(xml_path) and child_hrefs:
                    if update_xml_file(xml_path, child_hrefs, ditamap_dir):
                        relative_path = xml_path.relative_to(base_dir)
                        folder_name = relative_path.parent.name
                        file_name = relative_path.name
                        print(f"{folder_name}/{file_name}")
            except (ValueError, OSError):
                continue
    except etree.LxmlError:
        pass
    except Exception:
        pass

def main():
    """Main function to open DITAMAP selector and process files."""
    app = QApplication(sys.argv)
    ditamap_path = QFileDialog.getOpenFileName(
        None,
        "Select DITAMAP File",
        "",
        "DITAMAP Files (*.ditamap);;All Files (*)"
    )[0]
    if not ditamap_path:
        sys.exit(0)
    
    if not os.path.exists(ditamap_path):
        sys.exit(1)
    
    process_ditamap(ditamap_path)

if __name__ == "__main__":
    main()