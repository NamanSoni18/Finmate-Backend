# agents/sales_agent.py
import sys
import os

# Add the project root to the Python path to import our database utility
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.database import customer_db

class SalesAgent:
    """
    Discusses loan options with the customer and confirms the loan amount and tenure.
    """
    def __init__(self):
        pass

    def discuss_loan(self, phone_number, requested_amount, desired_tenure=None):
        """
        Evaluates the requested amount against the customer's pre-approved limit
        and provides a recommendation.
        
        Args:
            phone_number (str): The customer's phone number.
            requested_amount (int): The amount the customer wants.
            desired_tenure (int, optional): The tenure the customer wants.
            
        Returns:
            dict: A dictionary with the recommended amount, tenure, and a message.
        """
        print(f"[Sales Agent] Discussing loan options for phone: {phone_number}")
        
        customer = customer_db.get_customer_by_phone(phone_number)
        
        if not customer:
            return {"status": "error", "message": "Customer not found."}

        pre_approved_limit = customer['pre_approved_limit']
        
        # Default tenure logic if not provided
        if not desired_tenure:
            # A simple heuristic: longer tenure for larger amounts
            if requested_amount > 500000:
                desired_tenure = 72
            else:
                desired_tenure = 60
        
        # Logic to confirm or suggest the amount
        if requested_amount <= pre_approved_limit:
            print(f"[Sales Agent] ✅ Requested amount ₹{requested_amount:,} is within the pre-approved limit of ₹{pre_approved_limit:,}.")
            return {
                "status": "confirmed",
                "message": f"That's a great choice! An amount of ₹{requested_amount:,} is well within your pre-approved limit. Let's proceed with this for a tenure of {desired_tenure} months.",
                "final_amount": requested_amount,
                "final_tenure": desired_tenure
            }
        else:
            print(f"[Sales Agent] ⚠️ Requested amount ₹{requested_amount:,} exceeds the pre-approved limit of ₹{pre_approved_limit:,}.")
            return {
                "status": "suggestion",
                "message": f"I see you've requested ₹{requested_amount:,}. Based on your profile, your instant approval limit is ₹{pre_approved_limit:,}. We can certainly try for a higher amount, but it would require additional verification. For an instant approval, would you like to proceed with ₹{pre_approved_limit:,}?",
                "suggested_amount": pre_approved_limit,
                "final_tenure": desired_tenure
            }

# --- Self-test for the agent ---
if __name__ == '__main__':
    agent = SalesAgent()
    
    # --- Test Case 1: Amount within limit (Rajesh Kumar) ---
    print("--- TEST 1: Amount within pre-approved limit ---")
    # Rajesh has a limit of 500,000. Requesting 400,000 should be confirmed.
    result = agent.discuss_loan("9876543210", 400000)
    print(f"Result: {result}\n")

    # --- Test Case 2: Amount exceeds limit (Rajesh Kumar) ---
    print("--- TEST 2: Amount exceeds pre-approved limit ---")
    # Rajesh has a limit of 500,000. Requesting 800,000 should trigger a suggestion.
    result = agent.discuss_loan("9876543210", 800000)
    print(f"Result: {result}\n")