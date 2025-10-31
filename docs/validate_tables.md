# Validate Tables 


Scans XML files for `<table>` elements, checking title and column width.

**Input:** Path of the Topics/Chapters folder. 

**Output:**

Reports `<table>` elements with missing titles, total width >6.75 inches, or unspecified width (unless colwidth="1*").
