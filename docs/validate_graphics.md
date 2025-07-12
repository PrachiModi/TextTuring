# Validate Graphics

Scans XML files for `<image>` elements, checking width, scope, scale, and figure title.

**Input:** Path of the Topics/Chapters folder. 

**Output:**

Reports `<image>` elements with invalid width (missing, wrong unit, >6.75in), external scope, scale attribute, or missing figure title.
