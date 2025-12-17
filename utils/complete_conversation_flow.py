import os
import sys
import re
import random
from typing import Dict, List, Any, Optional

class CompleteConversationFlow:
    """Complete conversation flow for loan application with proper handling of edge cases"""
    
    def __init__(self):
        self.conversation_state = "greeting"
        self.conversation_history = []
        self.application_data = {}
        
        # Define conversation states
        self.states = {
            "greeting": {
                "entry_message": "Welcome to FinMate! I'm here to help you with your personal loan needs. To get started, could you please provide your 10-digit mobile number?",
                "next_states": ["mobile_verification", "help"]
            },
            "mobile_verification": {
                "entry_message": "Thank you! I've found your profile.",
                "next_states": ["loan_offer", "help"]
            },
            "loan_offer": {
                "entry_message": "Congratulations! 🎉 You are pre-approved for a personal loan up to {pre_approved_limit}. How much would you like to borrow?",
                "next_states": ["loan_amount", "help"]
            },
            "loan_amount": {
                "entry_message": "Great. And for how many months would you like the tenure?",
                "next_states": ["loan_tenure", "help"]
            },
            "loan_tenure": {
                "entry_message": "Thank you. I'm processing your request.",
                "next_states": ["loan_assessment", "help"]
            },
            "loan_assessment": {
                "entry_message": "",
                "next_states": ["offer", "rejection", "offer_exceeding_limit", "help"]
            },
            "offer": {
                "entry_message": "Congratulations! Your loan has been approved.",
                "next_states": ["offer_acceptance", "goodbye"]
            },
            "offer_exceeding_limit": {
                "entry_message": "",
                "next_states": ["offer_acceptance", "rejection", "help"]
            },
            "rejection": {
                "entry_message": "Unfortunately, your application could not be approved.",
                "next_states": ["help", "goodbye"]
            },
            "offer_acceptance": {
                "entry_message": "Thank you for accepting our offer! We'll process your loan shortly.",
                "next_states": ["goodbye"]
            },
            "help": {
                "entry_message": "I can help you with loan applications, check eligibility, and answer questions about our loan products.",
                "next_states": ["greeting", "loan_offer", "help"]
            },
            "goodbye": {
                "entry_message": "Thank you for using FinMate. Have a great day!",
                "next_states": []
            }
        }
    
    def extract_entities(self, text: str) -> Dict[str, Any]:
        """Extract entities from user's message"""
        entities = {}
        text = text.lower().strip()
        
        # Extract mobile number
        mobile_match = re.search(r'(\d{10})', text)
        if mobile_match:
            entities["mobile"] = mobile_match.group(1)
        
        # Extract loan amount
        loan_match = re.search(r'(?:loan|amount|borrow|request|need)\s*(?:of|for)?\s*(?:rs\.?|rupees?|₹)?\s*([0-9,]+)', text)
        if loan_match:
            try:
                entities["loan_amount"] = int(loan_match.group(1).replace(",", ""))
            except ValueError:
                pass
        
        # Extract tenure
        tenure_match = re.search(r'(?:tenure|months?|for)\s*([0-9]+)', text)
        if tenure_match:
            try:
                entities["tenure"] = int(tenure_match.group(1))
            except ValueError:
                pass
        
        # Extract yes/no
        if "yes" in text:
            entities["response"] = "yes"
        elif "no" in text:
            entities["response"] = "no"
        
        return entities
    
    def generate_response(self, message: str) -> Dict[str, Any]:
        """Generate a response based on the current state and user message"""
        # Extract entities
        entities = self.extract_entities(message)
        
        # Update application data
        for key, value in entities.items():
            if key in self.application_data or value:
                self.application_data[key] = value
        
        # Generate response based on current state
        if self.conversation_state == "greeting":
            if "mobile" in entities:
                self.conversation_state = "mobile_verification"
                return {
                    "response": "Thank you! I've found your profile.",
                    "state": self.conversation_state,
                    "options": []
                }
            else:
                return {
                    "response": self.states["greeting"]["entry_message"],
                    "state": self.conversation_state,
                    "options": []
                }
        
        elif self.conversation_state == "mobile_verification":
            # Generate pre-approved limit based on mobile (for demo purposes)
            # In a real system, this would come from a CRM or database
            mobile = entities.get("mobile", "9876543210")
            pre_approved_limit = 200000 if mobile == "9876543210" else 300000
            
            self.application_data["pre_approved_limit"] = pre_approved_limit
            self.conversation_state = "loan_offer"
            
            return {
                "response": self.states["loan_offer"]["entry_message"].format(
                    pre_approved_limit=f"₹{pre_approved_limit:,}"
                ),
                "state": self.conversation_state,
                "options": []
            }
        
        elif self.conversation_state == "loan_offer":
            if "loan_amount" in entities:
                self.conversation_state = "loan_amount"
                return {
                    "response": self.states["loan_amount"]["entry_message"],
                    "state": self.conversation_state,
                    "options": []
                }
            else:
                return {
                    "response": "Please enter the loan amount you would like to borrow (e.g., 300000).",
                    "state": self.conversation_state,
                    "options": []
                }
        
        elif self.conversation_state == "loan_amount":
            if "tenure" in entities:
                self.conversation_state = "loan_tenure"
                return {
                    "response": self.states["loan_tenure"]["entry_message"],
                    "state": self.conversation_state,
                    "options": []
                }
            else:
                return {
                    "response": "Please enter the tenure in months (e.g., 54).",
                    "state": self.conversation_state,
                    "options": []
                }
        
        elif self.conversation_state == "loan_tenure":
            # Assess the loan application
            assessment_result = self.assess_loan_application()
            self.conversation_state = assessment_result["state"]
            
            return {
                "response": assessment_result["response"],
                "state": self.conversation_state,
                "options": assessment_result.get("options", [])
            }
        
        elif self.conversation_state == "offer_exceeding_limit":
            if entities.get("response") == "yes":
                # Proceed with pre-approved limit
                self.application_data["loan_amount"] = self.application_data["pre_approved_limit"]
                self.conversation_state = "offer"
                return {
                    "response": self.states["offer"]["entry_message"],
                    "state": self.conversation_state,
                    "options": ["Accept offer", "View details", "Check other options"]
                }
            elif entities.get("response") == "no":
                # Try for higher amount (which would be rejected in this demo)
                assessment_result = self.assess_loan_application(try_higher=True)
                self.conversation_state = assessment_result["state"]
                return {
                    "response": assessment_result["response"],
                    "state": self.conversation_state,
                    "options": assessment_result.get("options", [])
                }
            else:
                return {
                    "response": "Please respond with 'yes' to proceed with the instant approval amount or 'no' to try for a higher amount.",
                    "state": self.conversation_state,
                    "options": ["Yes, proceed with instant approval", "No, try for higher amount"]
                }
        
        elif self.conversation_state == "offer":
            if entities.get("response") == "yes" or "accept" in message.lower():
                self.conversation_state = "offer_acceptance"
                return {
                    "response": self.states["offer_acceptance"]["entry_message"],
                    "state": self.conversation_state,
                    "options": []
                }
            else:
                return {
                    "response": "Would you like to accept this offer? Please respond with 'yes' or 'no'.",
                    "state": self.conversation_state,
                    "options": ["Yes, accept offer", "No, decline offer"]
                }
        
        elif self.conversation_state == "rejection":
            if "help" in message.lower():
                self.conversation_state = "help"
                return {
                    "response": self.states["help"]["entry_message"],
                    "state": self.conversation_state,
                    "options": ["Start new application", "Check eligibility criteria", "Speak to representative"]
                }
            else:
                self.conversation_state = "goodbye"
                return {
                    "response": "This conversation has concluded. Please refresh page to start a new one.",
                    "state": self.conversation_state,
                    "options": []
                }
        
        elif self.conversation_state == "offer_acceptance":
            self.conversation_state = "goodbye"
            return {
                "response": self.states["goodbye"]["entry_message"],
                "state": self.conversation_state,
                "options": []
            }
        
        elif self.conversation_state == "help":
            if "start" in message.lower() or "new" in message.lower():
                self.reset_conversation()
                return {
                    "response": self.states["greeting"]["entry_message"],
                    "state": self.conversation_state,
                    "options": []
                }
            else:
                return {
                    "response": "I can help you with loan applications, check eligibility, and answer questions about our loan products. What would you like to know?",
                    "state": self.conversation_state,
                    "options": ["Start new application", "Check eligibility criteria", "Speak to representative"]
                }
        
        # Default response
        return {
            "response": "I'm not sure I understand. Could you please rephrase your question or type 'help' for assistance?",
            "state": self.conversation_state,
            "options": ["Help", "Start new application"]
        }
    
    def assess_loan_application(self, try_higher=False) -> Dict[str, Any]:
        """Assess the loan application and return the result"""
        # Get application data
        loan_amount = self.application_data.get("loan_amount", 0)
        pre_approved_limit = self.application_data.get("pre_approved_limit", 0)
        
        # Generate a mock credit score (for demo purposes)
        # In a real system, this would come from a credit bureau
        credit_score = random.randint(650, 850)
        self.application_data["credit_score"] = credit_score
        
        # If trying for higher amount, reduce credit score to simulate rejection
        if try_higher:
            credit_score = random.randint(600, 699)
            self.application_data["credit_score"] = credit_score
        
        # Assess the application
        if credit_score < 700:
            return {
                "response": f"Unfortunately, your application could not be approved as your credit score ({credit_score}) is below our minimum requirement.",
                "state": "rejection",
                "options": ["Check eligibility criteria", "Start new application", "Speak to representative"]
            }
        elif loan_amount > pre_approved_limit:
            return {
                "response": f"I see you've requested ₹{loan_amount:,}. Based on your profile, your instant approval limit is ₹{pre_approved_limit:,}. We can certainly try for a higher amount, but it would require additional verification. For an instant approval, would you like to proceed with ₹{pre_approved_limit:,}?",
                "state": "offer_exceeding_limit",
                "options": ["Yes, proceed with instant approval", "No, try for higher amount"]
            }
        else:
            return {
                "response": f"Congratulations! Based on your profile, we can approve your loan request of ₹{loan_amount:,}.",
                "state": "offer",
                "options": ["Accept offer", "View details", "Check other options"]
            }
    
    def reset_conversation(self):
        """Reset the conversation"""
        self.conversation_state = "greeting"
        self.conversation_history = []
        self.application_data = {}
    
    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get the conversation history"""
        return self.conversation_history
    
    def get_conversation_state(self) -> str:
        """Get the current conversation state"""
        return self.conversation_state