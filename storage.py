import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from collections import defaultdict

import gspread
from oauth2client.service_account import ServiceAccountCredentials

import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BillStorage:
    """Google Sheets storage for bill data."""
    
    def __init__(self):
        """Initialize connection to Google Sheets."""
        try:
            if not config.GOOGLE_CREDENTIALS_PATH:
                raise Exception("Google credentials path not configured")
            
            if not config.GOOGLE_SHEET_ID:
                raise Exception("Google Sheet ID not configured")
            
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]
            
            credentials = ServiceAccountCredentials.from_json_keyfile_name(
                config.GOOGLE_CREDENTIALS_PATH,
                scope
            )
            
            client = gspread.authorize(credentials)
            self.sheet = client.open_by_key(config.GOOGLE_SHEET_ID).sheet1
            
            logger.info("Successfully connected to Google Sheets")
            
            self.setup_headers()
            
        except Exception as e:
            logger.error(f"Failed to initialize BillStorage: {e}")
            raise Exception(f"Storage initialization failed: {str(e)}")
    
    def setup_headers(self):
        """Set up column headers if sheet is empty."""
        try:
            first_row = self.sheet.row_values(1)
            
            if not first_row or all(cell == '' for cell in first_row):
                headers = [
                    'ID', 'Vendor', 'Vendor Address', 'Bill Date', 'Due Date',
                    'Invoice Number', 'Total Amount', 'Subtotal', 'Tax', 'Discount',
                    'Currency', 'Category', 'Line Items', 'Payment Status',
                    'Payment Method', 'Is Anomaly', 'Is Duplicate', 'Rule Violations',
                    'Risk Score', 'Recommendation', 'Processed At', 'Source'
                ]
                
                self.sheet.update('A1:V1', [headers])
                logger.info("Headers set up in Google Sheet")
            else:
                logger.info("Headers already exist in Google Sheet")
                
        except Exception as e:
            logger.error(f"Failed to setup headers: {e}")
            raise Exception(f"Header setup failed: {str(e)}")
    
    def save_bill(self, bill_dict: Dict, anomaly_report: Dict, source: str = "upload") -> str:
        """
        Save bill data to Google Sheets.
        
        Args:
            bill_dict: Bill data dictionary
            anomaly_report: Anomaly detection report
            source: Source of the bill (e.g., "upload", "telegram")
            
        Returns:
            Bill ID
        """
        try:
            line_items_str = str(bill_dict.get('line_items', []))
            violations_str = ', '.join(anomaly_report.get('rule_violations', []))
            
            row = [
                bill_dict.get('id', ''),
                bill_dict.get('vendor_name', ''),
                bill_dict.get('vendor_address', ''),
                bill_dict.get('bill_date', ''),
                bill_dict.get('due_date', ''),
                bill_dict.get('invoice_number', ''),
                bill_dict.get('total_amount', 0),
                bill_dict.get('subtotal', ''),
                bill_dict.get('tax_amount', ''),
                bill_dict.get('discount_amount', ''),
                bill_dict.get('currency', ''),
                bill_dict.get('category', ''),
                line_items_str,
                bill_dict.get('payment_status', ''),
                bill_dict.get('payment_method', ''),
                anomaly_report.get('is_anomaly', False),
                anomaly_report.get('is_duplicate', False),
                violations_str,
                anomaly_report.get('risk_score', 0),
                anomaly_report.get('recommendation', ''),
                bill_dict.get('processed_at', ''),
                source
            ]
            
            self.sheet.append_row(row)
            logger.info(f"Bill saved to Google Sheets: {bill_dict.get('id', 'Unknown')}")
            
            return bill_dict.get('id', '')
            
        except Exception as e:
            logger.error(f"Failed to save bill: {e}")
            raise Exception(f"Bill save failed: {str(e)}")
    
    def get_all_bills(self) -> List[Dict]:
        """
        Get all bills from Google Sheets.
        
        Returns:
            List of bill dictionaries
        """
        try:
            all_records = self.sheet.get_all_records()
            
            bills = []
            for record in all_records:
                bill = {}
                for key, value in record.items():
                    if key in ['Total Amount', 'Subtotal', 'Tax', 'Discount', 'Risk Score']:
                        try:
                            bill[key] = float(value) if value != '' else None
                        except (ValueError, TypeError):
                            bill[key] = None
                    elif key in ['Is Anomaly', 'Is Duplicate']:
                        bill[key] = str(value).lower() in ['true', '1', 'yes']
                    else:
                        bill[key] = value
                
                bills.append(bill)
            
            logger.info(f"Retrieved {len(bills)} bills from Google Sheets")
            return bills
            
        except Exception as e:
            logger.error(f"Failed to get all bills: {e}")
            return []
    
    def get_bills_by_category(self, category: str) -> List[Dict]:
        """
        Get bills filtered by category.
        
        Args:
            category: Category to filter by
            
        Returns:
            List of bills in the specified category
        """
        try:
            all_bills = self.get_all_bills()
            filtered = [
                bill for bill in all_bills 
                if bill.get('Category', '').lower() == category.lower()
            ]
            
            logger.info(f"Found {len(filtered)} bills in category '{category}'")
            return filtered
            
        except Exception as e:
            logger.error(f"Failed to get bills by category: {e}")
            return []
    
    def get_upcoming_due(self, days: int = 7) -> List[Dict]:
        """
        Get unpaid bills due within the next N days.
        
        Args:
            days: Number of days to look ahead
            
        Returns:
            List of upcoming due bills sorted by due date
        """
        try:
            all_bills = self.get_all_bills()
            today = datetime.now()
            future_date = today + timedelta(days=days)
            
            upcoming = []
            for bill in all_bills:
                payment_status = bill.get('Payment Status', '').lower()
                if payment_status == 'paid':
                    continue
                
                due_date_str = bill.get('Due Date', '')
                if not due_date_str:
                    continue
                
                try:
                    due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
                    if today <= due_date <= future_date:
                        upcoming.append(bill)
                except (ValueError, TypeError):
                    continue
            
            upcoming.sort(key=lambda x: x.get('Due Date', ''))
            
            logger.info(f"Found {len(upcoming)} bills due within {days} days")
            return upcoming
            
        except Exception as e:
            logger.error(f"Failed to get upcoming due bills: {e}")
            return []
    
    def get_anomalies(self) -> List[Dict]:
        """
        Get all bills flagged as anomalies.
        
        Returns:
            List of anomalous bills
        """
        try:
            all_bills = self.get_all_bills()
            anomalies = [
                bill for bill in all_bills 
                if bill.get('Is Anomaly', False)
            ]
            
            logger.info(f"Found {len(anomalies)} anomalous bills")
            return anomalies
            
        except Exception as e:
            logger.error(f"Failed to get anomalies: {e}")
            return []
    
    def update_status(self, bill_id: str, new_status: str) -> bool:
        """
        Update payment status of a bill.
        
        Args:
            bill_id: ID of the bill to update
            new_status: New payment status
            
        Returns:
            True if updated successfully
        """
        try:
            all_values = self.sheet.get_all_values()
            
            for idx, row in enumerate(all_values[1:], start=2):
                if row[0] == bill_id:
                    self.sheet.update_cell(idx, 14, new_status)
                    logger.info(f"Updated bill {bill_id} status to '{new_status}'")
                    return True
            
            logger.warning(f"Bill ID {bill_id} not found")
            return False
            
        except Exception as e:
            logger.error(f"Failed to update status: {e}")
            return False
    
    def get_summary(self) -> Dict:
        """
        Get summary statistics of all bills.
        
        Returns:
            Dictionary with summary statistics
        """
        try:
            all_bills = self.get_all_bills()
            
            total_amount = 0.0
            total_bills = len(all_bills)
            anomaly_count = 0
            by_category = defaultdict(float)
            monthly = defaultdict(float)
            
            for bill in all_bills:
                amount = bill.get('Total Amount')
                if amount:
                    total_amount += amount
                
                if bill.get('Is Anomaly', False):
                    anomaly_count += 1
                
                category = bill.get('Category', 'other')
                if amount:
                    by_category[category] += amount
                
                bill_date = bill.get('Bill Date', '')
                if bill_date:
                    try:
                        date_obj = datetime.strptime(bill_date, '%Y-%m-%d')
                        month_key = date_obj.strftime('%Y-%m')
                        if amount:
                            monthly[month_key] += amount
                    except (ValueError, TypeError):
                        pass
            
            top_category = max(by_category.items(), key=lambda x: x[1])[0] if by_category else 'none'
            
            summary = {
                'total_amount': round(total_amount, 2),
                'total_bills': total_bills,
                'anomaly_count': anomaly_count,
                'by_category': dict(by_category),
                'monthly': dict(monthly),
                'top_category': top_category
            }
            
            logger.info(f"Generated summary: {total_bills} bills, ${total_amount:.2f} total")
            return summary
            
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return {
                'total_amount': 0.0,
                'total_bills': 0,
                'anomaly_count': 0,
                'by_category': {},
                'monthly': {},
                'top_category': 'none'
            }


storage = BillStorage()


if __name__ == "__main__":
    logger.info("Testing BillStorage")
    
    try:
        test_bill = {
            'id': 'test-123',
            'vendor_name': 'Test Vendor',
            'vendor_address': '123 Test St',
            'bill_date': '2024-01-15',
            'due_date': '2024-02-15',
            'invoice_number': 'INV-001',
            'total_amount': 100.50,
            'subtotal': 90.00,
            'tax_amount': 10.50,
            'discount_amount': 0,
            'currency': 'USD',
            'category': 'shopping',
            'line_items': [],
            'payment_status': 'unpaid',
            'payment_method': None,
            'processed_at': datetime.utcnow().isoformat()
        }
        
        test_anomaly = {
            'is_anomaly': False,
            'is_duplicate': False,
            'rule_violations': [],
            'risk_score': 10,
            'recommendation': 'approve',
            'ml_confidence': 0.0
        }
        
        bill_id = storage.save_bill(test_bill, test_anomaly, 'test')
        print(f"Saved test bill: {bill_id}")
        
        summary = storage.get_summary()
        print("\nSummary:")
        print(f"Total Bills: {summary['total_bills']}")
        print(f"Total Amount: ${summary['total_amount']}")
        print(f"Anomalies: {summary['anomaly_count']}")
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
