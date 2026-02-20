import logging
import requests
from typing import Dict, Any
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def send_telegram_notification(bill_data: Dict[str, Any], anomaly_report: Dict[str, Any]) -> bool:
    """
    Send Telegram notification for processed bill.
    
    Args:
        bill_data: Parsed bill data
        anomaly_report: Anomaly detection report
        
    Returns:
        True if notification sent successfully, False otherwise
    """
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not configured, skipping notification")
        return False
    
    try:
        risk_score = anomaly_report.get('risk_score', 0)
        
        # Determine if high risk (>= 70)
        if risk_score >= 70:
            message = _format_high_risk_message(bill_data, anomaly_report)
        else:
            message = _format_success_message(bill_data, anomaly_report)
        
        # Send via Telegram Bot API
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        
        logger.info(f"Telegram notification sent successfully (risk score: {risk_score})")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {e}")
        return False


def _format_high_risk_message(bill_data: Dict[str, Any], anomaly_report: Dict[str, Any]) -> str:
    """Format high-risk alert message."""
    vendor = bill_data.get('vendor_name', 'Unknown')
    amount = bill_data.get('total_amount', 0)
    risk_score = anomaly_report.get('risk_score', 0)
    recommendation = anomaly_report.get('recommendation', 'Review carefully')
    violations = anomaly_report.get('rule_violations', [])
    
    message = f"⚠️ <b>HIGH RISK BILL DETECTED!</b>\n\n"
    message += f"🏪 <b>Vendor:</b> {vendor}\n"
    message += f"💰 <b>Amount:</b> ${amount:.2f}\n"
    message += f"⚠️ <b>Risk Score:</b> {risk_score}/100\n"
    message += f"📊 <b>Recommendation:</b> {recommendation}\n"
    
    if violations:
        message += f"\n🚫 <b>Violations:</b> {', '.join(violations)}"
    
    return message


def _format_success_message(bill_data: Dict[str, Any], anomaly_report: Dict[str, Any]) -> str:
    """Format success notification message."""
    vendor = bill_data.get('vendor_name', 'Unknown')
    amount = bill_data.get('total_amount', 0)
    category = bill_data.get('category', 'Other')
    due_date = bill_data.get('due_date', 'N/A')
    risk_score = anomaly_report.get('risk_score', 0)
    
    message = f"✅ <b>Bill Processed Successfully!</b>\n\n"
    message += f"🏪 <b>Vendor:</b> {vendor}\n"
    message += f"💰 <b>Amount:</b> ${amount:.2f}\n"
    message += f"📁 <b>Category:</b> {category}\n"
    message += f"📅 <b>Due Date:</b> {due_date}\n"
    message += f"✓ <b>Risk Score:</b> {risk_score}/100"
    
    return message


if __name__ == "__main__":
    # Test notification
    test_bill = {
        "vendor_name": "Test Vendor",
        "total_amount": 50.00,
        "category": "Utilities",
        "due_date": "2026-03-01"
    }
    
    test_anomaly = {
        "risk_score": 25,
        "recommendation": "Bill looks normal",
        "rule_violations": []
    }
    
    logger.info("Testing Telegram notification...")
    success = send_telegram_notification(test_bill, test_anomaly)
    
    if success:
        logger.info("✅ Test notification sent successfully!")
    else:
        logger.error("❌ Test notification failed")
