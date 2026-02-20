import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Optional

from openai import OpenAI

import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_bill(raw_text: str) -> dict:
    """
    Parse raw OCR text into structured bill data using OpenAI GPT-4o-mini.
    
    Args:
        raw_text: Raw text extracted from bill/invoice
        
    Returns:
        Dictionary with structured bill data
        
    Raises:
        Exception: If parsing fails after retry
    """
    if not config.OPENAI_API_KEY:
        raise Exception("OpenAI API key not configured")
    
    if not raw_text or not raw_text.strip():
        raise Exception("Raw text is empty")
    
    logger.info("Starting bill parsing with OpenAI GPT-4o-mini")
    
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    
    system_prompt = "You are an expert invoice and bill parser. Extract all fields accurately. Return ONLY valid JSON, no extra text, no markdown code blocks."
    
    user_prompt = f"""Extract all information from this bill and return as JSON with this exact schema:
{{
  'vendor_name': string,
  'vendor_address': string or null,
  'bill_date': 'YYYY-MM-DD' or null,
  'due_date': 'YYYY-MM-DD' or null,
  'invoice_number': string or null,
  'total_amount': number,
  'subtotal': number or null,
  'tax_amount': number or null,
  'discount_amount': number or null,
  'currency': 'USD' or 'INR' or 'EUR' etc,
  'category': one of [food, utilities, travel, shopping, medical, entertainment, subscription, other],
  'line_items': [{{'description': string, 'quantity': number, 'unit_price': number, 'total': number}}],
  'payment_status': 'paid' or 'unpaid' or 'unknown',
  'payment_method': string or null
}}

Bill text: {raw_text}"""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1
        )
        
        content = response.choices[0].message.content
        logger.info("Received response from OpenAI")
        
        bill_dict = _parse_json_response(content)
        bill_dict = _validate_and_fix_bill(bill_dict)
        
        logger.info(f"Successfully parsed bill: {bill_dict.get('vendor_name', 'Unknown')}")
        return bill_dict
        
    except Exception as e:
        logger.warning(f"First parsing attempt failed: {e}. Retrying with simpler prompt...")
        return _retry_simple_parse(client, raw_text)


def _parse_json_response(content: str) -> dict:
    """Parse JSON from OpenAI response, handling markdown code blocks."""
    content = content.strip()
    
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    
    if content.endswith("```"):
        content = content[:-3]
    
    content = content.strip()
    
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing failed: {e}")
        raise Exception(f"Failed to parse JSON response: {str(e)}")


def _validate_and_fix_bill(bill_dict: dict) -> dict:
    """Validate required fields and attempt to fix missing data."""
    required_fields = ['vendor_name', 'total_amount', 'currency', 'category']
    
    for field in required_fields:
        if field not in bill_dict:
            logger.warning(f"Missing required field: {field}")
            if field == 'vendor_name':
                bill_dict[field] = "Unknown Vendor"
            elif field == 'currency':
                bill_dict[field] = "USD"
            elif field == 'category':
                bill_dict[field] = "other"
            elif field == 'total_amount':
                bill_dict[field] = 0
    
    if not bill_dict.get('total_amount') or bill_dict['total_amount'] == 0:
        line_items = bill_dict.get('line_items', [])
        if line_items:
            calculated_total = sum(item.get('total', 0) for item in line_items)
            if calculated_total > 0:
                bill_dict['total_amount'] = calculated_total
                logger.info(f"Calculated total_amount from line_items: {calculated_total}")
    
    return bill_dict


def _retry_simple_parse(client: OpenAI, raw_text: str) -> dict:
    """Retry parsing with a simpler prompt focusing on essential fields."""
    simple_prompt = f"""Extract the vendor name, total amount, and date from this bill. Return as JSON:
{{
  'vendor_name': string,
  'total_amount': number,
  'bill_date': 'YYYY-MM-DD' or null,
  'currency': 'USD' or 'INR' or 'EUR' etc
}}

Bill text: {raw_text}"""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Extract basic bill information. Return only valid JSON."},
                {"role": "user", "content": simple_prompt}
            ],
            temperature=0.1
        )
        
        content = response.choices[0].message.content
        bill_dict = _parse_json_response(content)
        
        bill_dict.setdefault('vendor_address', None)
        bill_dict.setdefault('due_date', None)
        bill_dict.setdefault('invoice_number', None)
        bill_dict.setdefault('subtotal', None)
        bill_dict.setdefault('tax_amount', None)
        bill_dict.setdefault('discount_amount', None)
        bill_dict.setdefault('category', 'other')
        bill_dict.setdefault('line_items', [])
        bill_dict.setdefault('payment_status', 'unknown')
        bill_dict.setdefault('payment_method', None)
        
        logger.info("Successfully parsed with simplified prompt")
        return bill_dict
        
    except Exception as e:
        logger.error(f"Retry parsing also failed: {e}")
        raise Exception(f"Failed to parse bill after retry: {str(e)}")


def enrich_bill(bill_dict: dict) -> dict:
    """
    Enrich bill data with additional metadata and normalization.
    
    Args:
        bill_dict: Parsed bill dictionary
        
    Returns:
        Enriched bill dictionary with ID, timestamp, and normalized data
    """
    logger.info("Enriching bill data")
    
    enriched = bill_dict.copy()
    
    enriched['id'] = str(uuid.uuid4())
    enriched['processed_at'] = datetime.utcnow().isoformat() + 'Z'
    
    if 'currency' in enriched and enriched['currency']:
        enriched['currency'] = enriched['currency'].upper()
    
    for date_field in ['bill_date', 'due_date']:
        if date_field in enriched and enriched[date_field]:
            try:
                date_obj = datetime.fromisoformat(enriched[date_field].replace('Z', '+00:00'))
                enriched[date_field] = date_obj.strftime('%Y-%m-%d')
            except Exception as e:
                logger.warning(f"Could not normalize {date_field}: {e}")
    
    if 'category' in enriched and enriched['category']:
        enriched['category'] = enriched['category'].lower()
    
    if 'payment_status' in enriched and enriched['payment_status']:
        enriched['payment_status'] = enriched['payment_status'].lower()
    
    logger.info(f"Bill enriched with ID: {enriched['id']}")
    return enriched


if __name__ == "__main__":
    test_text = """
    ACME Store
    123 Main Street, New York, NY 10001
    
    Invoice #: INV-2024-001
    Date: 2024-01-15
    
    Item                Qty    Price    Total
    Widget A            2      $10.00   $20.00
    Widget B            1      $15.00   $15.00
    
    Subtotal:                           $35.00
    Tax (8%):                           $2.80
    Total:                              $37.80
    
    Payment: Credit Card
    Status: PAID
    """
    
    logger.info("Testing bill parser")
    try:
        parsed = parse_bill(test_text)
        enriched = enrich_bill(parsed)
        
        print("\n" + "="*50)
        print("PARSED AND ENRICHED BILL:")
        print("="*50)
        print(json.dumps(enriched, indent=2))
        print("="*50)
    except Exception as e:
        logger.error(f"Test failed: {e}")
