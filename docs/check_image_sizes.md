# Check Image Size

Scans the graphics directory for JPEG and PNG images, identifying those requiring resizing based on width (>1000px) or file size (>1MB).

**Input:** Path to the graphics directory.

**Output:**

**Resize Images resizes all large images according to Tech Pubs' requiements. 

Original images are backed up to the `LegacyTextTuring/Graphics` folder, and all modifications are logged to `LegacyTextTuring/Log.txt`.