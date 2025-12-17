# agents/underwriting_agent.py
import sys
import os

# Add the project root to the Python path to import our agents
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.risk_assessment_agent import RiskAssessmentAgent

class UnderwritingAgent:
    """
    Evaluates loan applications based on credit score and pre-approved limits.
    This agent calls external mock APIs to fetch necessary data.
    """
    def __init__(self):
        self.risk_assessment_agent = RiskAssessmentAgent()

    def evaluate_loan(self, phone_number, requested_amount):
        """
        Evaluates a loan request against business rules.
        
        Args:
            phone_number (str): The customer's phone number.
            requested_amount (int): The loan amount requested by the customer.
            
        Returns:
            dict: A dictionary with the decision, reason, and details.
        """
        print(
            f"[Underwriting Agent] Evaluating loan request for ₹{requested_amount:,} for phone: {phone_number}"
        )

        try:
            amount = int(requested_amount)
        except Exception:
            return {"status": "error", "message": "Requested amount must be a number."}

        decision = self.risk_assessment_agent.assess(phone_number, amount)
        if decision.get("status") in {"approved_instant", "pending_salary_slip", "rejected"}:
            return decision
        return {"status": "error", "message": decision.get("message") or "A system error occurred."}

# --- Self-test for the agent ---
if __name__ == '__main__':
    agent = UnderwritingAgent()

    def _run_case(label: str, phone: str, amount: int) -> None:
        print(label)
        result = agent.evaluate_loan(phone, amount)
        if result.get("status") == "error" and result.get("message") == "Customer not found.":
            print(f"Result: {result} (skipped: customer not in DB)\n")
            return
        print(f"Result: {result}\n")
    
    # --- Test Case 1: Instant Approval ---
    # Uses phone numbers that may/may not exist depending on your DB seed.
    _run_case("\n--- TEST 1: Instant Approval ---", "9876543210", 400000)

    # --- Test Case 2: Requires Salary Slip ---
    _run_case("--- TEST 2: Requires Salary Slip ---", "9876543210", 800000)

    # --- Test Case 3: Rejection due to Credit Score ---
    _run_case("--- TEST 3: Rejection due to Credit Score ---", "1234567890", 100000)

    # --- Test Case 4: Rejection due to High Amount ---
    _run_case("--- TEST 4: Rejection due to High Amount ---", "9876543210", 1200000)