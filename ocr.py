import os
import base64
import logging
import tempfile
import requests
from pathlib import Path
from typing import Optional

from PIL import Image
from pdf2image import convert_from_path
from pillow_heif import register_heif_opener

import config

# Register HEIF opener to support HEIC images
register_heif_opener()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# OCR.space API endpoint (Free tier: 25,000 requests/month)
OCR_SPACE_API_URL = "https://api.ocr.space/parse/image"
OCR_SPACE_API_KEY = "K87899142388957"  # Free public API key


def extract_text(file_path: str) -> str:
    """
    Extract text from image or PDF file using OCR.space API (free).
    
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
        
        text = _extract_with_ocr_space(image_path)
        logger.info("Successfully extracted text using OCR.space API")
        
        cleaned_text = _clean_text(text)
        return cleaned_text
        
    except Exception as e:
        logger.error(f"Error extracting text from {file_path}: {e}")
        raise Exception(f"Failed to extract text: {str(e)}")
    
    finally:
        if temp_image_path and os.path.exists(temp_image_path):
            os.unlink(temp_image_path)
            logger.debug(f"Cleaned up temporary file: {temp_image_path}")


def _extract_with_ocr_space(image_path: str) -> str:
    """Extract text using OCR.space API (free tier: 25,000 requests/month)."""
    try:
        with open(image_path, 'rb') as image_file:
            payload = {
                'apikey': OCR_SPACE_API_KEY,
                'language': 'eng',
                'isOverlayRequired': False,
                'detectOrientation': True,
                'scale': True,
                'OCREngine': 2,
            }
            
            response = requests.post(
                OCR_SPACE_API_URL,
                files={'file': image_file},
                data=payload,
                timeout=30
            )
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('IsErroredOnProcessing'):
                error_msg = result.get('ErrorMessage', ['Unknown error'])[0]
                raise Exception(f"OCR.space API error: {error_msg}")
            
            if result.get('ParsedResults'):
                text = result['ParsedResults'][0].get('ParsedText', '')
                return text
            
            return ""
            
    except requests.exceptions.RequestException as e:
        raise Exception(f"OCR.space API request failed: {str(e)}")
    except Exception as e:
        raise Exception(f"OCR.space processing failed: {str(e)}")




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
