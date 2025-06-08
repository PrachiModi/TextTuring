import cv2
import numpy as np
import os
import logging
import time
import errno
from PIL import Image

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
DARK_THRESHOLD = 180  # Grayscale threshold for dark pixels
BORDER_WIDTH = 1      # Pixel width of border to check
NEW_BORDER_COLOR = 0  # Black in grayscale (0=black, 255=white)
NEW_BORDER_SIZE = 2   # 2-pixel border
ALPHA_THRESHOLD = 50  # Alpha threshold for transparency

def is_border_dark(border_pixels, alpha_pixels=None, border_name="unknown", image_name="unknown"):
    """Check if border has sufficient dark pixels (below threshold)."""
    try:
        logger.debug(f"{image_name} - {border_name} border: Input shape: {border_pixels.shape}")
        if alpha_pixels is not None:
            opaque_mask = alpha_pixels > ALPHA_THRESHOLD
            logger.debug(f"{image_name} - {border_name} border: Opaque pixels count: {np.sum(opaque_mask)}/{alpha_pixels.size}")
            logger.debug(f"{image_name} - {border_name} border alpha values: {alpha_pixels.ravel().tolist()}")
            if not np.any(opaque_mask):
                logger.debug(f"{image_name} - {border_name} border is fully or mostly transparent")
                return False
            valid_pixels = border_pixels[opaque_mask]
        else:
            valid_pixels = border_pixels

        if valid_pixels.size == 0:
            logger.debug(f"{image_name} - {border_name} border: No valid pixels")
            return False

        logger.debug(f"{image_name} - {border_name} border raw values: {valid_pixels.reshape(-1, valid_pixels.shape[-1]).tolist()}")

        if valid_pixels.ndim == 3 and valid_pixels.shape[-1] == 3:
            gray_pixels = cv2.cvtColor(valid_pixels, cv2.COLOR_BGR2GRAY).ravel()
        elif valid_pixels.ndim == 2 or (valid_pixels.ndim == 3 and valid_pixels.shape[-1] == 1):
            gray_pixels = valid_pixels.ravel()
        else:
            logger.error(f"{image_name} - {border_name} border: Invalid pixel shape: {valid_pixels.shape}")
            return False

        min_value = np.min(gray_pixels) if gray_pixels.size > 0 else 255
        max_value = np.max(gray_pixels) if gray_pixels.size > 0 else 255
        mean_value = np.mean(gray_pixels) if gray_pixels.size > 0 else 255
        dark_count = np.sum(gray_pixels < DARK_THRESHOLD) if gray_pixels.size > 0 else 0
        total_count = gray_pixels.size if gray_pixels.size > 0 else 1
        dark_ratio = dark_count / total_count
        logger.debug(f"{image_name} - {border_name} border stats: min={min_value:.2f}, max={max_value:.2f}, "
                     f"mean={mean_value:.2f}, dark pixels={dark_count}/{total_count} ({dark_ratio:.2%})")
        logger.debug(f"{image_name} - {border_name} border grayscale values: {gray_pixels.tolist()}")

        return dark_ratio > 0.5
    except Exception as e:
        logger.error(f"{image_name} - Error processing {border_name} border pixels: {str(e)}")
        return False

def has_black_border(image_path):
    """
    Check if the image has dark borders on all sides.
    Returns: (has_border: bool, status: str, reason: str)
    """
    try:
        image_name = os.path.basename(image_path)
        if not os.path.exists(image_path):
            logger.error(f"Image file not found: {image_path}")
            return False, "Corrupted", "Error: File not found"
        if not os.access(image_path, os.R_OK):
            logger.error(f"No read permission for image: {image_path}")
            return False, "Access denied", "Error: Permission denied"

        # Pre-validate with Pillow
        try:
            with open(image_path, 'rb') as f:
                pil_img = Image.open(f)
                if pil_img is None:
                    logger.error(f"PIL failed to open {image_path}: Image object is None")
                    return False, "Corrupted", "Error: Invalid image format: None"
                pil_img.verify()

            with open(image_path, 'rb') as f:
                pil_img = Image.open(f)
                width, height = pil_img.size
                mode = pil_img.mode

        except Exception as e:
            logger.error(f"PIL failed to open {image_path}: {str(e)}")
            return False, "Corrupted", f"Error: Invalid image format: {str(e)}"

        logger.debug(f"PIL Image: {image_name}, Dimensions: {width}x{height}, Mode: {mode}")
        if height < 2 or width < 2:
            logger.error(f"Image too small: {image_path}, Dimensions: {width}x{height}")
            return False, "Corrupted", "Error: Image dimensions too small"

        if mode == 'P':
            logger.debug(f"{image_name} - Converting P mode to RGBA for transparency check")
            has_transparency = pil_img.info.get('transparency') is not None or 'tRNS' in pil_img.info.get('pnginfo', {})
            pil_img = pil_img.convert('RGBA' if has_transparency else 'RGB')
            mode = pil_img.mode
            logger.debug(f"{image_name} - Converted to Mode: {mode}")

        if mode not in ('L', 'RGB', 'RGBA'):
            logger.error(f"Unsupported image mode: {image_path}, Mode: {mode}")
            return False, "Corrupted", f"Error: Unsupported image mode: {mode}"

        if mode == 'L':
            img = np.array(pil_img)
            channels = 1
        else:
            img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
            if img is None:
                logger.error(f"Failed to load image with OpenCV: {image_path}")
                return False, "Corrupted", "Error: Could not load image"
            channels = img.shape[2] if img.ndim == 3 else 1

        logger.debug(f"Image: {image_name}, Dimensions: {width}x{height}, Channels: {channels}")

        if np.any(np.isnan(img)) or np.any(np.isinf(img)):
            logger.error(f"Invalid pixel data in image: {image_path}")
            return False, "Corrupted", "Error: Invalid pixel data"

        if channels == 4:
            alpha = img[:, :, 3]
            color_img = img[:, :, :3]
            expected_border_channels = 3
            logger.debug(f"{image_name} - Alpha channel min/max: {np.min(alpha)}/{np.max(alpha)}")
        elif channels == 3:
            alpha = None
            color_img = img
            expected_border_channels = 3
        elif channels == 1:
            alpha = None
            color_img = img
            expected_border_channels = 1
        else:
            logger.error(f"Unsupported channel count: {channels} for {image_path}")
            return False, "Corrupted", f"Error: Unsupported image format (channels: {channels})"

        try:
            if channels in (3, 4):
                top_border = color_img[0:BORDER_WIDTH, :, :]
                bottom_border = color_img[-BORDER_WIDTH:, :, :]
                left_border = color_img[:, 0:BORDER_WIDTH, :]
                right_border = color_img[:, -BORDER_WIDTH:, :]
                borders = [("top", top_border), ("bottom", bottom_border), 
                          ("left", left_border), ("right", right_border)]
                for border_name, border in borders:
                    logger.debug(f"{image_name} - {border_name} border shape: {border.shape}")
                    if border.ndim != 3 or border.shape[-1] != expected_border_channels or border.size == 0:
                        logger.error(f"Invalid {border_name} border shape for {image_path}: {border.shape}")
                        return False, "Corrupted", f"Error: Invalid border shape for {border_name}"
            else:
                top_border = color_img[0:BORDER_WIDTH, :]
                bottom_border = color_img[-BORDER_WIDTH:, :]
                left_border = color_img[:, 0:BORDER_WIDTH]
                right_border = color_img[:, -BORDER_WIDTH:]
                borders = [("top", top_border), ("bottom", bottom_border), 
                          ("left", left_border), ("right", right_border)]
                for border_name, border in borders:
                    logger.debug(f"{image_name} - {border_name} border shape: {border.shape}")
                    if border.ndim != 2 or border.size == 0 or border.shape[0] == 0 or border.shape[1] == 0:
                        logger.error(f"Invalid {border_name} border shape for {image_path}: {border.shape}")
                        return False, "Corrupted", f"Error: Invalid grayscale border shape for {border_name}"
        except Exception as e:
            logger.error(f"Failed to extract borders for {image_path}: {str(e)}")
            return False, "Corrupted", f"Error: Failed to extract borders: {str(e)}"

        top_alpha = alpha[0:BORDER_WIDTH, :] if alpha is not None else None
        bottom_alpha = alpha[-BORDER_WIDTH:, :] if alpha is not None else None
        left_alpha = alpha[:, 0:BORDER_WIDTH] if alpha is not None else None
        right_alpha = alpha[:, -BORDER_WIDTH:] if alpha is not None else None

        borders_status = {
            "top": is_border_dark(top_border, top_alpha, "top", image_name),
            "bottom": is_border_dark(bottom_border, bottom_alpha, "bottom", image_name),
            "left": is_border_dark(left_border, left_alpha, "left", image_name),
            "right": is_border_dark(right_border, right_alpha, "right", image_name)
        }

        logger.debug(f"{image_name} - Border status: Top: {borders_status['top']}, "
                     f"Bottom: {borders_status['bottom']}, Left: {borders_status['left']}, Right: {borders_status['right']}")

        dark_borders = sum(borders_status.values())
        if dark_borders == 4:
            return True, "Has dark borders", "All borders are dark"
        else:
            return False, "Missing dark borders", f"Detected {dark_borders}/4 dark borders"

    except PermissionError as e:
        logger.error(f"Permission error processing {image_path}: {str(e)}")
        return False, "Access denied", f"Error: Permission denied: {str(e)}"
    except FileNotFoundError as e:
        logger.error(f"File not found: {image_path}: {str(e)}")
        return False, "Corrupted", f"Error: File not found: {str(e)}"
    except Exception as e:
        logger.error(f"Error processing {image_path}: {str(e)}")
        return False, "Corrupted", f"Error: {str(e)}"

def add_black_border(image_path):
    """
    Add a 2-pixel black border to the image with full opacity and overwrite it.
    Returns: bool indicating success
    """
    try:
        image_name = os.path.basename(image_path)
        logger.debug(f"Adding 2-pixel black border to {image_path}")
        if not os.path.exists(image_path):
            logger.error(f"Image file not found for border addition: {image_path}")
            return False
        if not os.access(image_path, os.W_OK):
            logger.error(f"No write permission for image: {image_path}")
            return False

        # Load with Pillow
        try:
            with open(image_path, 'rb') as f:
                pil_img = Image.open(f)
                if pil_img is None:
                    logger.error(f"PIL failed to open {image_path}: Image object is None")
                    return False
                if pil_img.mode == 'P':
                    has_transparency = pil_img.info.get('transparency') is not None or 'tRNS' in pil_img.info.get('pnginfo', {})
                    pil_img = pil_img.convert('RGBA' if has_transparency else 'RGB')
                    logger.debug(f"{image_name} - Converted P mode to {pil_img.mode}")
                img = np.array(pil_img)
        except Exception as e:
            logger.error(f"PIL failed to open {image_path}: {str(e)}")
            return False

        logger.debug(f"{image_name} - Image array shape: {img.shape}")
        if img.shape[2] == 3:
            alpha = np.full((img.shape[0], img.shape[1]), 255, dtype=np.uint8)
            img = np.dstack((img, alpha))
        elif img.shape[2] == 1:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            alpha = np.full((img.shape[0], img.shape[1]), 255, dtype=np.uint8)
            img = np.dstack((img, alpha))
        elif img.shape[2] != 4:
            logger.error(f"Unsupported image format: {image_path}, channels: {img.shape[2]}")
            return False

        bordered_img = cv2.copyMakeBorder(
            img,
            NEW_BORDER_SIZE, NEW_BORDER_SIZE, NEW_BORDER_SIZE, NEW_BORDER_SIZE,
            cv2.BORDER_CONSTANT,
            value=[0, 0, 0, 255]
        )

        for attempt in range(3):
            try:
                success = cv2.imwrite(image_path, bordered_img, [cv2.IMWRITE_PNG_COMPRESSION, 9])
                if success:
                    logger.debug(f"Added 2-pixel black border to {image_path}")
                    return True
                logger.warning(f"Failed to save bordered image: {image_path}, attempt {attempt + 1}/3")
                time.sleep(0.1)
            except Exception as e:
                logger.warning(f"Failed to save bordered image: {image_path}, attempt {attempt + 1}/3, error: {str(e)}")
                time.sleep(0.1)

        logger.error(f"Failed to save bordered image after retries: {image_path}")
        return False

    except PermissionError as e:
        logger.error(f"Permission error adding border to {image_path}: {str(e)}")
        return False
    except FileNotFoundError as e:
        logger.error(f"File not found for border addition: {image_path}: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Failed to add border to {image_path}: {str(e)}")
        return False

if __name__ == "__main__":
    logger.error("This module is not meant to be run directly. Import it in your main application (e.g., main.py).")
    exit(1)