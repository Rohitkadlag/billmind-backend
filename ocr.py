import os
import base64
import logging
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image
from pdf2image import convert_from_path
from google.cloud import vision
from google.oauth2 import service_account
from pillow_heif import register_heif_opener

import config

# Register HEIF opener to support HEIC images
register_heif_opener()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def extract_text(file_path: str) -> str:
    """
    Extract text from image or PDF file using Google Cloud Vision API.
    Falls back to pytesseract if Vision API is unavailable.
    
    Args:
        file_path: Path to image or PDF file
        
    Returns:
        Extracted text as clean string
        
    Raises:
        FileNotFoundError: If file doesn't exist
        Exception: For other processing errors
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    file_ext = Path(file_path).suffix.lower()
    temp_image_path = None
    
    try:
        if file_ext == '.pdf':
            logger.info(f"Converting PDF to image: {file_path}")
            pages = convert_from_path(file_path, first_page=1, last_page=1)
            
            if not pages:
                raise Exception("Failed to convert PDF to image")
            
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                temp_image_path = tmp.name
                pages[0].save(temp_image_path, 'PNG')
            
            image_path = temp_image_path
        else:
            image_path = file_path
        
        try:
            text = _extract_with_vision_api(image_path)
            logger.info("Successfully extracted text using Google Cloud Vision API")
        except Exception as vision_error:
            logger.warning(f"Vision API failed: {vision_error}. Falling back to pytesseract")
            text = _extract_with_tesseract(image_path)
        
        cleaned_text = _clean_text(text)
        return cleaned_text
        
    except Exception as e:
        logger.error(f"Error extracting text from {file_path}: {e}")
        raise Exception(f"Failed to extract text: {str(e)}")
    
    finally:
        if temp_image_path and os.path.exists(temp_image_path):
            os.unlink(temp_image_path)
            logger.debug(f"Cleaned up temporary file: {temp_image_path}")


def _extract_with_vision_api(image_path: str) -> str:
    """Extract text using Google Cloud Vision API."""
    if not config.GOOGLE_CREDENTIALS_PATH or not os.path.exists(config.GOOGLE_CREDENTIALS_PATH):
        raise Exception("Google credentials not found or not configured")
    
    credentials = service_account.Credentials.from_service_account_file(
        config.GOOGLE_CREDENTIALS_PATH
    )
    client = vision.ImageAnnotatorClient(credentials=credentials)
    
    with open(image_path, 'rb') as image_file:
        content = image_file.read()
    
    image = vision.Image(content=content)
    response = client.text_detection(image=image)
    
    if response.error.message:
        raise Exception(f"Vision API error: {response.error.message}")
    
    texts = response.text_annotations
    if texts:
        return texts[0].description
    
    return ""


def _extract_with_tesseract(image_path: str) -> str:
    """Fallback OCR using pytesseract."""
    temp_converted_path = None
    try:
        import pytesseract
        
        # Always convert to PNG for maximum tesseract compatibility
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            temp_converted_path = tmp.name
        
        # Open image and convert to RGB
        image = Image.open(image_path)
        if image.mode not in ('RGB', 'L'):
            image = image.convert('RGB')
        
        # Save as PNG
        image.save(temp_converted_path, 'PNG')
        logger.info(f"Converted image to PNG for tesseract: {temp_converted_path}")
        
        # Process the PNG file
        text = pytesseract.image_to_string(Image.open(temp_converted_path))
        logger.info("Successfully extracted text using pytesseract")
        return text
        
    except ImportError:
        raise Exception("pytesseract not installed. Install with: pip install pytesseract")
    except Exception as e:
        raise Exception(f"Tesseract extraction failed: {str(e)}")
    finally:
        if temp_converted_path and os.path.exists(temp_converted_path):
            os.unlink(temp_converted_path)
            logger.debug(f"Cleaned up converted file: {temp_converted_path}")


def _clean_text(text: str) -> str:
    """Remove extra whitespace and empty lines from text."""
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return '\n'.join(lines)


def file_to_base64(file_path: str) -> str:
    """
    Read file and return base64 encoded string.
    
    Args:
        file_path: Path to file
        
    Returns:
        Base64 encoded string
        
    Raises:
        FileNotFoundError: If file doesn't exist
        Exception: For other reading errors
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    try:
        with open(file_path, 'rb') as f:
            file_bytes = f.read()
        
        encoded = base64.b64encode(file_bytes).decode('utf-8')
        logger.info(f"Successfully encoded file to base64: {file_path}")
        return encoded
        
    except Exception as e:
        logger.error(f"Error encoding file to base64: {e}")
        raise Exception(f"Failed to encode file: {str(e)}")


def base64_to_text(base64_str: str) -> str:
    """
    Decode base64 string to image and extract text.
    
    Args:
        base64_str: Base64 encoded image string
        
    Returns:
        Extracted text
        
    Raises:
        Exception: For decoding or extraction errors
    """
    temp_file_path = None
    
    try:
        image_bytes = base64.b64decode(base64_str)
        
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            temp_file_path = tmp.name
            tmp.write(image_bytes)
        
        logger.info(f"Decoded base64 to temporary file: {temp_file_path}")
        text = extract_text(temp_file_path)
        return text
        
    except Exception as e:
        logger.error(f"Error processing base64 string: {e}")
        raise Exception(f"Failed to process base64: {str(e)}")
    
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
            logger.debug(f"Cleaned up temporary file: {temp_file_path}")


if __name__ == "__main__":
    test_image_path = "./test_bill.png"
    
    if os.path.exists(test_image_path):
        logger.info(f"Testing OCR with: {test_image_path}")
        try:
            text = extract_text(test_image_path)
            print("\n" + "="*50)
            print("EXTRACTED TEXT:")
            print("="*50)
            print(text)
            print("="*50)
        except Exception as e:
            logger.error(f"Test failed: {e}")
    else:
        logger.warning(f"Test image not found: {test_image_path}")
        logger.info("Place a test image at ./test_bill.png to run the test")
