import sys
import os
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QFileDialog
from lxml import etree
from urllib.parse import unquote
import uuid

def is_empty_except_title(xml_path):
    """Check if an XML file contains only a title element and no other significant content."""
    try:
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(str(xml_path), parser)
        root = tree.getroot()
        
        # Get all child elements of the root
        children = [child for child in root if etree.iselement(child)]
        
        # Find title element
        title_elements = root.xpath("//title")
        
        # Check if there's exactly one title and no other significant content
        has_title = len(title_elements) == 1
        has_other_content = False
        
        # Check for other elements that might contain content
        for child in children:
            if child.tag != "title":
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

def update_xml_file(xml_path, child_hrefs):
    """Update an XML file with a conbody containing xrefs to child hrefs."""
    try:
        parser = etree.XMLParser(recover=True, remove_blank_text=True)
        tree = etree.parse(str(xml_path), parser)
        root = tree.getroot()
        
        # Preserve original title and root attributes
        title = root.find("title")
        if title is None:
            return False
        
        # Create conbody
        conbody = etree.SubElement(root, "conbody")
        p = etree.SubElement(conbody, "p")
        p.text = "This chapter contains the following topics: "
        ul = etree.SubElement(p, "ul", id=f"ul_{uuid.uuid4().hex[:12]}")
        
        # Add xref for each child href
        for href in child_hrefs:
            li = etree.SubElement(ul, "li")
            xref = etree.SubElement(li, "xref", href=href)
        
        # Write updated XML back to file
        tree.write(str(xml_path), encoding="UTF-8", xml_declaration=True, doctype=root.getroottree().docinfo.doctype, pretty_print=True)
        return True
    except etree.LxmlError:
        return False
    except Exception:
        return False

def process_ditamap(ditamap_path):
    """Process a DITAMAP file and update empty XML files."""
    base_dir = Path(ditamap_path).parent
    try:
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(str(ditamap_path), parser)
        namespaces = {'dita': 'http://dita.oasis-open.org/architecture/2005/'}
        
        # Find all topicref elements
        topicrefs = tree.xpath("//dita:topicref | //topicref | //dita:chapter | //chapter", namespaces=namespaces)
        
        for topicref in topicrefs:
            href = topicref.get("href")
            if not href:
                continue
            
            # Decode URL-encoded href for file path resolution
            decoded_href = unquote(href)
            try:
                xml_path = (base_dir / decoded_href).resolve()
                if not xml_path.exists():
                    continue
                if xml_path.suffix.lower() not in ('.xml', '.dita'):
                    continue
                
                # Get child topicref hrefs (keep original encoding)
                child_hrefs = [child.get("href").split('/')[-1] for child in topicref.xpath("./dita:topicref | ./topicref", namespaces=namespaces) if child.get("href")]
                
                if is_empty_except_title(xml_path) and child_hrefs:
                    if update_xml_file(xml_path, child_hrefs):
                        # Print updated file path
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
    ditamap_path, _ = QFileDialog.getOpenFileName(
        None,
        "Select DITAMAP File",
        "",
        "DITAMAP Files (*.ditamap);;All Files (*)"
    )
    if not ditamap_path:
        sys.exit(0)
    
    if not os.path.exists(ditamap_path):
        sys.exit(1)
    
    process_ditamap(ditamap_path)

if __name__ == "__main__":
    main()