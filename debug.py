import os
import json
import logging
from PIL import Image, UnidentifiedImageError
import io

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("image_metadata.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def extract_image_metadata(file_path: str) -> dict:
    """Extract metadata from an image file."""
    metadata = {
        "file_path": file_path,
        "file_size_bytes": 0,
        "format": None,
        "size": None,
        "mode": None,
        "info": {},
        "exif": None,
        "icc_profile": None,
        "is_corrupted": False,
        "error": None
    }
    
    try:
        # Validate file
        if not os.path.exists(file_path):
            metadata["error"] = "File not found"
            return metadata
        if not os.access(file_path, os.R_OK):
            metadata["error"] = "No read permission"
            return metadata
        
        # File size
        metadata["file_size_bytes"] = os.path.getsize(file_path)
        
        # Open image
        with Image.open(file_path) as img:
            metadata["format"] = img.format
            metadata["size"] = img.size
            metadata["mode"] = img.mode
            metadata["info"] = dict(img.info)
            
            # EXIF data
            exif = img.getexif()
            if exif:
                metadata["exif"] = {k: v for k, v in exif.items()}
            
            # ICC profile
            icc = img.info.get("icc_profile")
            if icc:
                metadata["icc_profile"] = f"Present (length: {len(icc)} bytes)"
            
            # Check corruption
            try:
                img.verify()
            except Exception as e:
                metadata["is_corrupted"] = True
                metadata["error"] = f"Verification failed: {str(e)}"
                return metadata
            
            # Reopen for further checks
            with Image.open(file_path) as img:
                try:
                    img.load()
                except Exception as e:
                    metadata["is_corrupted"] = True
                    metadata["error"] = f"Pixel data load failed: {str(e)}"
    
    except UnidentifiedImageError as e:
        metadata["is_corrupted"] = True
        metadata["error"] = f"Unidentified image: {str(e)}"
    except Exception as e:
        metadata["error"] = f"Unexpected error: {str(e)}"
    
    return metadata

def scan_directory(directory_path: str) -> list:
    """Recursively scan directory for all image files."""
    results = []
    try:
        for root, _, files in os.walk(directory_path):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    # Try opening as image to check if it's a valid image file
                    with Image.open(file_path):
                        logger.info(f"Processing: {file_path}")
                        metadata = extract_image_metadata(file_path)
                        results.append(metadata)
                        logger.info(f"Metadata for {file_path}:\n{json.dumps(metadata, indent=2, default=str)}")
                except (UnidentifiedImageError, Exception):
                    continue  # Skip non-image files
        if not results:
            logger.warning(f"No image files found in {directory_path} or its subfolders")
    except Exception as e:
        logger.error(f"Error scanning directory: {str(e)}")
    return results

def save_report(results: list, output_path: str):
    """Save metadata to JSON file."""
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"Report saved to {output_path}")
    except Exception as e:
        logger.error(f"Failed to save report: {str(e)}")

if __name__ == "__main__":
    directory_path = '/Users/prachi.modi/Downloads/CV-CUE User Guide 13.0.1/User Guide/Graphics/Monitoring WiFi'
    if not os.path.isdir(directory_path):
        logger.error(f"Directory not found: {directory_path}")
        exit(1)
    
    logger.info(f"Scanning directory and subfolders: {directory_path}")
    results = scan_directory(directory_path)
    output_file = "image_metadata_report.json"
    save_report(results, output_file)
    logger.info(f"Scan complete. Check {output_file} and image_metadata.log for details.")