# agents/master_agent.py
import sys
import os
import re

# Add the project root to the Python path to import our other agents
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.verification_agent import VerificationAgent
from agents.sales_agent import SalesAgent
from agents.underwriting_agent import UnderwritingAgent
from agents.sanction_letter_generator import SanctionLetterGenerator
from agents.document_verification_agent import DocumentVerificationAgent
from agents.credit_bureau_agent import CreditBureauAgent
from agents.risk_assessment_agent import RiskAssessmentAgent
from agents.central_context_agent import CentralContextAgent
from agents.conversation_agent import ConversationAgent
from agents.sentiment_analysis_agent import SentimentAnalysisAgent  # Add this import

class MasterAgent:
    """
    The main orchestrator for the loan sales process.
    Manages the conversation flow and coordinates the Worker Agents.
    """
    def __init__(self):
        # Initialize all worker agents
        self.verification_agent = VerificationAgent()
        self.sales_agent = SalesAgent()
        self.underwriting_agent = UnderwritingAgent()
        self.sanction_generator = SanctionLetterGenerator()

        # Newly added agents for the project
        self.document_verification_agent = DocumentVerificationAgent()
        self.credit_bureau_agent = CreditBureauAgent()
        self.risk_assessment_agent = RiskAssessmentAgent()
        self.central_context_agent = CentralContextAgent()
        self.conversation_agent = ConversationAgent(self.central_context_agent)
        self.sentiment_agent = SentimentAnalysisAgent()  # Initialize the sentiment agent
        
        # Store conversation state
        self.customer_details = None
        self.loan_details = {}
        self.current_session_id = "demo_session"  # For demo purposes

    def start_conversation(self):
        """Initiates the conversation with the customer."""
        print("Chatbot: Welcome to Tata Capital! I'm here to help you with your personal loan needs.")
        print("Chatbot: To get started, could you please provide your 10-digit mobile number?")
        
        # In a real web app, this would be an input field.
        # For our prototype, we'll simulate user input.
        phone = input("You: ")
        
        # Analyze sentiment of the first message
        sentiment_result = self.sentiment_agent.analyze_sentiment(phone)
        if os.environ.get("DEBUG_SENTIMENT") == "1":
            print(f"[Master Agent] Sentiment analysis: {sentiment_result}")
        
        # Simple validation
        if len(phone) == 10 and phone.isdigit():
            self.handle_verification(phone)
        else:
            print("Chatbot: That doesn't seem to be a valid 10-digit number. Let's try again.")
            self.start_conversation() # Restart the flow

    def handle_verification(self, phone):
        """Handles the customer verification step."""
        print("\n[Master Agent] Verifying customer...")
        verification_result = self.verification_agent.verify_customer(phone)
        
        if verification_result['status'] == 'success':
            self.customer_details = verification_result
            print(f"Chatbot: Thank you, {self.customer_details['name']}! I've found your profile.")
            self.handle_loan_request()
        else:
            print("Chatbot: I'm sorry, but I couldn't find an account associated with that number. Please check and try again.")
            self.start_conversation()

    def handle_loan_request(self):
        """Handles the loan amount and tenure request."""
        def _extract_amount(text: str):
            raw = (text or "").strip().lower()
            if not raw:
                return None
            m = re.search(r"(\d+(?:\.\d+)?)\s*(lakh|lakhs|lac|lacs)", raw)
            if m:
                return int(float(m.group(1)) * 100_000)
            m = re.search(r"(\d+(?:\.\d+)?)\s*(crore|crores)", raw)
            if m:
                return int(float(m.group(1)) * 10_000_000)
            m = re.search(r"(\d[\d,]{2,})", raw)
            if not m:
                return None
            try:
                return int(m.group(1).replace(",", ""))
            except ValueError:
                return None

        def _extract_tenure_months(text: str):
            raw = (text or "").strip().lower()
            if not raw:
                return None
            y = re.search(r"(\d+)\s*(year|years|yr|yrs)", raw)
            if y:
                return int(y.group(1)) * 12
            m = re.search(r"(\d+)\s*(month|months|mo|mos)?", raw)
            if m:
                try:
                    return int(m.group(1))
                except ValueError:
                    return None
            return None

        pre_limit = None
        try:
            pre_limit = int(self.customer_details.get("pre_approved_limit") or 0)
        except Exception:
            pre_limit = None

        # --- Amount collection ---
        while True:
            if pre_limit:
                print(
                    f"Chatbot: How much would you like to borrow? (Your pre-approved limit is ₹{pre_limit:,}. Example: 300000 or '3 lakh')"
                )
            else:
                print("Chatbot: How much would you like to borrow? (Example: 300000 or '3 lakh')")

            amount_str = input("You: ")
            sentiment_result = self.sentiment_agent.analyze_sentiment(amount_str)
            if os.environ.get("DEBUG_SENTIMENT") == "1":
                print(f"[Master Agent] Sentiment analysis: {sentiment_result}")

            detected = set(sentiment_result.get("detected_states", []) or [])
            if "confused" in detected:
                print(
                    "Chatbot: No worries — you can type the amount like '300000', '3 lakh', or '2.5 lakhs'."
                )
                continue
            if "negative" in detected:
                print("Chatbot: Sorry about that — I’ll make this quick and clear.")

            amount = _extract_amount(amount_str)
            if amount is None or amount <= 0:
                print(
                    "Chatbot: I couldn't understand the amount. Please enter like '300000' or '3 lakh'."
                )
                continue

            self.loan_details["requested_amount"] = amount
            break

        # --- Tenure collection ---
        while True:
            print("Chatbot: And what tenure would you like? (Example: 60, '23 months', or '2 years')")
            tenure_str = input("You: ")
            sentiment_result = self.sentiment_agent.analyze_sentiment(tenure_str)
            if os.environ.get("DEBUG_SENTIMENT") == "1":
                print(f"[Master Agent] Sentiment analysis: {sentiment_result}")

            detected = set(sentiment_result.get("detected_states", []) or [])
            if "confused" in detected:
                print(
                    "Chatbot: Tenure is just the number of months you want to repay (e.g., 24 months = 2 years)."
                )
                continue

            tenure = _extract_tenure_months(tenure_str)
            if tenure is None or tenure <= 0:
                print("Chatbot: Please enter tenure like '60' or '23 months' or '2 years'.")
                continue

            self.loan_details["tenure"] = tenure
            break

        self.handle_sales_discussion()

    def handle_sales_discussion(self):
        """Discusses the loan options with the sales agent."""
        print("\n[Master Agent] Discussing loan options...")
        sales_result = self.sales_agent.discuss_loan(
            self.customer_details['phone'], 
            self.loan_details['requested_amount'],
            self.loan_details['tenure']
        )
        
        print(f"Chatbot: {sales_result['message']}")
        
        if sales_result['status'] == 'suggestion':
            # In a real app, this would be a button click. Here we simulate with text.
            choice = input("Type 'yes' to accept the suggested amount, or 'no' to continue with your original request: ").lower()
            
            # Analyze sentiment of the choice
            sentiment_result = self.sentiment_agent.analyze_sentiment(choice)
            print(f"[Master Agent] Sentiment analysis: {sentiment_result}")
            
            # Check for escalation based on sentiment
            if self.sentiment_agent.should_escalate(sentiment_result):
                response = self._handle_escalation(sentiment_result)
                print(f"Chatbot: {response}")
                self.end_conversation("escalated")
                return
            
            if choice == 'yes':
                self.loan_details['final_amount'] = sales_result['suggested_amount']
            else:
                self.loan_details['final_amount'] = self.loan_details['requested_amount']
        else:
            self.loan_details['final_amount'] = sales_result['final_amount']
        
        self.loan_details['final_tenure'] = sales_result['final_tenure']
        self.handle_underwriting()

    def handle_underwriting(self):
        """Handles the underwriting and approval process."""
        print("\n[Master Agent] Sending your application for evaluation...")
        underwriting_result = self.underwriting_agent.evaluate_loan(
            self.customer_details['phone'], 
            self.loan_details['final_amount']
        )
        
        status = underwriting_result['status']
        print(f"Chatbot: {underwriting_result['reason']}")

        if status == 'approved_instant':
            self.handle_approval(underwriting_result)
        elif status == 'pending_salary_slip':
            self.handle_salary_slip_upload()
        elif status == 'rejected':
            self.end_conversation("rejected")
        else:
            self.end_conversation("error")

    def handle_salary_slip_upload(self):
        """Handles the simulation of a salary slip upload."""
        print("Chatbot: Please upload a clear copy of your latest salary slip.")
        # Simulate file upload
        input("Press Enter after uploading the file...")
        
        # In a real product, we would parse the PDF/image here.
        # For the prototype, we assume the upload is successful and the salary is sufficient.
        print("\n[Master Agent] Verifying uploaded document... (Simulated)")
        print("[Master Agent] ✅ Document verified. EMI is within the 50% salary limit.")
        
        # Re-run underwriting with a flag to indicate documents are verified
        print("[Master Agent] Re-evaluating loan request...")
        # We'll just assume approval now for simplicity.
        # A more complex agent might call the underwriting agent with a new parameter.
        approval_result = {
            "status": "approved_instant",
            "reason": "Congratulations! Your loan has been approved after document verification.",
            "approved_amount": self.loan_details['final_amount']
        }
        self.handle_approval(approval_result)

    def handle_approval(self, approval_result):
        """Handles the final approval and generates the sanction letter."""
        self.loan_details['approved_amount'] = approval_result['approved_amount']
        self.loan_details['interest_rate'] = "10.99%" # Get from offer mart API in a real product
        
        print("\n[Master Agent] Generating your sanction letter...")
        letter_result = self.sanction_generator.generate_letter(self.customer_details, self.loan_details)
        
        if letter_result['status'] == 'success':
            print(f"Chatbot: 🎉 Congratulations! Your loan of ₹{self.loan_details['approved_amount']:,} has been approved.")
            print(f"Chatbot: Your sanction letter '{letter_result['filename']}' has been generated.")
            print("Chatbot: You will receive a copy on your email and SMS shortly. Thank you for choosing Tata Capital!")
            self.end_conversation("approved")
        else:
            print("Chatbot: There was an issue generating your sanction letter. Please contact support.")
            self.end_conversation("error")
    
    def _handle_escalation(self, sentiment_result):
        """Handle escalation based on negative sentiment."""
        dominant_state = sentiment_result.get("dominant_state", "")
        
        if dominant_state == "negative":
            return "I understand your frustration. Let me connect you with a human agent who can better assist you. They will be with you shortly."
        elif dominant_state == "urgent":
            return "I understand this is urgent. Let me prioritize your request and connect you with a specialist immediately."
        else:
            return "I understand you need additional assistance. Let me connect you with a human agent who can help."

    def end_conversation(self, outcome):
        """Ends the conversation."""
        print("\n--- Conversation End ---")
        if outcome == "approved":
            print("Outcome: Loan Approved and Letter Generated.")
        elif outcome == "rejected":
            print("Outcome: Loan Rejected.")
        elif outcome == "escalated":
            print("Outcome: Escalated to Human Agent.")
        else:
            print("Outcome: Error during process.")
        print("Chatbot: Is there anything else I can help you with today?")

# --- Driver script to run the Master Agent ---
if __name__ == '__main__':
    # IMPORTANT: Make sure your mock API server is running in another terminal!
    master = MasterAgent()
    master.start_conversation()