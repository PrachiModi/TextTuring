# Ensure Unique IDs

Click **Remove Duplicate IDs** to scan XML and DITA files, renaming duplicate IDs and updating references.

**Input:** Path to the directory containing XML and DITA files.

**Output:**

- **Remove Duplicate IDs**:  
  Renames duplicate IDs with `ttu_` prefix and `_n` suffix, updating internal and cross-file `<xref>` and `<topicref>` references.

Original files are backed up to the `LegacyTextTuring` folder, and changes are logged to `LegacyTextTuring/Log.txt`.