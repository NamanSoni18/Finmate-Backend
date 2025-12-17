# agents/verification_agent.py
import sys
import os

# Add the project root to the Python path to import our database utility
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.database import customer_db

class VerificationAgent:
    """
    Responsible for verifying customer identity and fetching KYC details.
    In a real product, this would securely connect to a CRM or KYC service.
    """
    def __init__(self):
        pass

    def verify_customer(self, phone_number):
        """
        Verifies a customer based on their phone number.
        
        Args:
            phone_number (str): The customer's phone number.
            
        Returns:
            dict: A dictionary containing customer details if found, otherwise an error.
        """
        print(f"[Verification Agent] Attempting to verify customer with phone: {phone_number}")
        
        if not phone_number:
            return {"status": "error", "message": "Phone number cannot be empty."}

        customer = customer_db.get_customer_by_phone(phone_number)
        
        if customer:
            print(f"[Verification Agent] ✅ Successfully verified customer: {customer['name']}")
            # Return only the necessary KYC details, INCLUDING the pre-approved limit
            return {
                "status": "success",
                "customer_id": customer['customer_id'],
                "name": customer['name'],
                "phone": customer['phone'],
                "email": customer['email'],
                "address": customer['address'],
                "pre_approved_limit": customer['pre_approved_limit'] # <-- THIS IS THE FIX
            }
        else:
            print(f"[Verification Agent] ❌ Verification failed. No customer found with phone: {phone_number}")
            return {"status": "error", "message": "Customer not found."}

# Example of how we would test this agent directly
if __name__ == '__main__':
    agent = VerificationAgent()
    
    # Test with a valid customer
    print("--- Testing with a valid phone number ---")
    result = agent.verify_customer("9876543210")
    print(f"Result: {result}\n")
    
    # Test with an invalid customer
    print("--- Testing with an invalid phone number ---")
    result = agent.verify_customer("1234567890")
    print(f"Result: {result}\n")