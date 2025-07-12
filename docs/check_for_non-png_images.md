# Check for Non-PNG Images

Click **Convert to PNG** to transform identified images into PNGs, ensuring file size is under 1MB and both height and width do not exceed 1000 pixels.

**Input:** Path to the graphics directory.

**Output:**

- **Convert to PNG**:  
  Converts JPEG to PNG and replaces JPEG with PNG at the same location.
- **Update Links**:  
  Modifies XMLs to replace .jpeg/.jpg links with .png links.

Original images and XMLs are backed up to the `LegacyTextTuring/Graphics` folder, and all conversions are logged to `LegacyTextTuring/Log.txt`.