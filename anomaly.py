import os
import pickle
import logging
from datetime import datetime
from typing import List, Tuple, Dict, Optional

import pandas as pd
from sklearn.ensemble import IsolationForest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BillAnomalyDetector:
    """Anomaly detection for bills using ML and rule-based checks."""
    
    def __init__(self):
        """Initialize detector and load existing model/history if available."""
        self.model = None
        self.bills_history = pd.DataFrame()
        
        if os.path.exists('anomaly_model.pkl'):
            try:
                with open('anomaly_model.pkl', 'rb') as f:
                    self.model = pickle.load(f)
                logger.info("Loaded existing anomaly detection model")
            except Exception as e:
                logger.warning(f"Failed to load model: {e}")
                self.model = None
        
        if os.path.exists('bills_history.csv'):
            try:
                self.bills_history = pd.read_csv('bills_history.csv')
                logger.info(f"Loaded {len(self.bills_history)} bills from history")
            except Exception as e:
                logger.warning(f"Failed to load bills history: {e}")
                self.bills_history = pd.DataFrame()
    
    def train(self, bills_list: List[dict]):
        """
        Train IsolationForest model on historical bills data.
        
        Args:
            bills_list: List of bill dictionaries
        """
        if not bills_list:
            logger.warning("No bills provided for training")
            return
        
        logger.info(f"Training anomaly detector on {len(bills_list)} bills")
        
        df = pd.DataFrame(bills_list)
        
        if 'total_amount' not in df.columns or 'tax_amount' not in df.columns:
            logger.error("Required columns missing for training")
            return
        
        df['tax_amount'] = df['tax_amount'].fillna(0)
        
        training_data = df[['total_amount', 'tax_amount']].copy()
        
        self.model = IsolationForest(
            contamination=0.1,
            random_state=42,
            n_estimators=100
        )
        self.model.fit(training_data)
        
        try:
            with open('anomaly_model.pkl', 'wb') as f:
                pickle.dump(self.model, f)
            logger.info("Model saved to anomaly_model.pkl")
        except Exception as e:
            logger.error(f"Failed to save model: {e}")
        
        try:
            df.to_csv('bills_history.csv', index=False)
            self.bills_history = df
            logger.info("Bills history saved to bills_history.csv")
        except Exception as e:
            logger.error(f"Failed to save bills history: {e}")
    
    def check_ml_anomaly(self, amount: float, tax: float) -> Tuple[bool, float]:
        """
        Check if amount and tax combination is anomalous using ML model.
        
        Args:
            amount: Total amount
            tax: Tax amount
            
        Returns:
            Tuple of (is_anomaly, confidence_percentage)
        """
        if self.model is None:
            return (False, 0.0)
        
        try:
            data = pd.DataFrame([[amount, tax]], columns=['total_amount', 'tax_amount'])
            prediction = self.model.predict(data)[0]
            score = self.model.score_samples(data)[0]
            
            is_anomaly = prediction == -1
            
            confidence = abs(score) * 100
            confidence = min(max(confidence, 0), 100)
            
            logger.info(f"ML anomaly check: {'ANOMALY' if is_anomaly else 'NORMAL'} (confidence: {confidence:.1f}%)")
            return (is_anomaly, confidence)
            
        except Exception as e:
            logger.error(f"ML anomaly check failed: {e}")
            return (False, 0.0)
    
    def check_rules(self, bill: Dict) -> List[str]:
        """
        Check bill against rule-based validation rules.
        
        Args:
            bill: Bill dictionary
            
        Returns:
            List of violation strings
        """
        violations = []
        
        total_amount = bill.get('total_amount', 0)
        tax_amount = bill.get('tax_amount', 0) or 0
        vendor_name = bill.get('vendor_name', '')
        invoice_number = bill.get('invoice_number')
        due_date = bill.get('due_date')
        
        if total_amount > 50000:
            violations.append("Amount unusually high")
        
        if total_amount > 0 and tax_amount > (total_amount * 0.35):
            violations.append("Tax exceeds 35% of total")
        
        if due_date:
            try:
                due_date_obj = datetime.strptime(due_date, '%Y-%m-%d')
                if due_date_obj < datetime.now():
                    violations.append("Bill is overdue")
            except Exception as e:
                logger.warning(f"Could not parse due_date: {e}")
        
        if not vendor_name or vendor_name.strip() == '':
            violations.append("Vendor name missing")
        
        if total_amount <= 0:
            violations.append("Invalid amount")
        
        if not invoice_number:
            violations.append("Missing invoice number")
        
        if violations:
            logger.info(f"Rule violations found: {violations}")
        
        return violations
    
    def check_duplicate(self, bill: Dict, all_bills: List[Dict]) -> bool:
        """
        Check if bill is a duplicate based on vendor, amount, and date.
        
        Args:
            bill: Bill to check
            all_bills: List of existing bills
            
        Returns:
            True if duplicate found
        """
        vendor = bill.get('vendor_name', '').strip().lower()
        amount = bill.get('total_amount', 0)
        date = bill.get('bill_date', '')
        
        if not vendor or not date:
            return False
        
        for existing_bill in all_bills:
            existing_vendor = existing_bill.get('vendor_name', '').strip().lower()
            existing_amount = existing_bill.get('total_amount', 0)
            existing_date = existing_bill.get('bill_date', '')
            
            if (existing_vendor == vendor and 
                existing_amount == amount and 
                existing_date == date):
                logger.warning(f"Duplicate bill detected: {vendor}, {amount}, {date}")
                return True
        
        return False
    
    def full_check(self, bill: Dict, all_bills: List[Dict]) -> Dict:
        """
        Perform comprehensive anomaly check including ML, rules, and duplicates.
        
        Args:
            bill: Bill to check
            all_bills: List of existing bills for duplicate check
            
        Returns:
            Dictionary with anomaly analysis results
        """
        logger.info(f"Running full anomaly check for bill: {bill.get('vendor_name', 'Unknown')}")
        
        total_amount = bill.get('total_amount', 0)
        tax_amount = bill.get('tax_amount', 0) or 0
        
        is_ml_anomaly, ml_confidence = self.check_ml_anomaly(total_amount, tax_amount)
        
        rule_violations = self.check_rules(bill)
        
        is_duplicate = self.check_duplicate(bill, all_bills)
        
        risk_score = 0
        
        if is_ml_anomaly:
            risk_score += 40
        
        violation_penalty = min(len(rule_violations) * 20, 40)
        risk_score += violation_penalty
        
        if is_duplicate:
            risk_score += 30
        
        risk_score = min(risk_score, 100)
        
        if risk_score < 30:
            recommendation = "approve"
        elif risk_score < 70:
            recommendation = "review"
        else:
            recommendation = "reject"
        
        result = {
            "is_anomaly": is_ml_anomaly,
            "is_duplicate": is_duplicate,
            "rule_violations": rule_violations,
            "risk_score": risk_score,
            "recommendation": recommendation,
            "ml_confidence": ml_confidence
        }
        
        logger.info(f"Anomaly check complete - Risk: {risk_score}, Recommendation: {recommendation}")
        return result


detector = BillAnomalyDetector()


if __name__ == "__main__":
    logger.info("Testing BillAnomalyDetector")
    
    sample_bills = [
        {"vendor_name": "Store A", "total_amount": 100, "tax_amount": 10, "bill_date": "2024-01-01"},
        {"vendor_name": "Store B", "total_amount": 200, "tax_amount": 20, "bill_date": "2024-01-02"},
        {"vendor_name": "Store C", "total_amount": 150, "tax_amount": 15, "bill_date": "2024-01-03"},
        {"vendor_name": "Store D", "total_amount": 300, "tax_amount": 30, "bill_date": "2024-01-04"},
    ]
    
    detector.train(sample_bills)
    
    test_bill = {
        "vendor_name": "Store E",
        "total_amount": 100000,
        "tax_amount": 50,
        "bill_date": "2024-01-05",
        "due_date": "2023-12-01",
        "invoice_number": None
    }
    
    result = detector.full_check(test_bill, sample_bills)
    
    print("\n" + "="*50)
    print("ANOMALY CHECK RESULT:")
    print("="*50)
    print(f"Is Anomaly: {result['is_anomaly']}")
    print(f"Is Duplicate: {result['is_duplicate']}")
    print(f"Rule Violations: {result['rule_violations']}")
    print(f"Risk Score: {result['risk_score']}")
    print(f"Recommendation: {result['recommendation']}")
    print(f"ML Confidence: {result['ml_confidence']:.1f}%")
    print("="*50)
