Validate HTML
============

Scans HTML output to validate internal links, external links, and images. Identifies broken internal links, missing images, or invalid external links, logging results with file references.

**Input:** index.html file of your guide

**Scans:**

\-**Internal Links**: Verifies all referenced HTML files exist in the out folder.

\- **Graphics**: Ensures images in HTML files exist in the out/Graphics folder.

\- **External Links**: Checks external links for redirects or broken URLs.Large projects may take several minutes to process.