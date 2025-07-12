# Check for Empty XML Files

Scans all XML files referenced in .ditamap to check for empty xmls containing only the XML title tag. Adds a table of contents to empty XMLS. 

**Input:** Path to the DITAMAP file.

**Output:**

**Fix** or **Fix All** updates empty XML files with a mini-TOC containing xref links to child topics.

Original XMLs are backed up to the `LegacyTextTuring` folder, and all updates are logged to `LegacyTextTuring/Log.txt`.