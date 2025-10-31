

Validate PDF
============

Scans your PDF and checks for PDF metadata, links, and overflowing table cells.

**Input:** PDF output of the guide.

Validate Links
--------------

Checks for external hyperlinks and validates them. Identifies redirected, invalid, and unreachable links, logging results with page references.

**Example Output:**

*   Redirected: http://example.com → http://new-url.com (Page 3)
    
*   Invalid: http://broken.com (Status: 404, Page 5)
    
*   Unreachable: http://timeout.com (Timeout, Page 7)
    

**Performance:** 
- Small PDFs (< 100 pages): ~10-20 seconds
- Medium PDFs (100-500 pages): ~30-60 seconds  
- Large PDFs (500-1000 pages): 1-2 minutes
- Very Large PDFs (1000-5000+ pages): 3-6 minutes

Uses adaptive worker scaling: 16 workers for small PDFs, up to 32 workers for PDFs over 1000 pages.

Validate Tables
---------------

Scans the entire PDF for cells with overflowing content.

**Example:**   

![Overflow Example](./image.png)

**Note:** Large PDFs may take up to 5 minutes to process.
