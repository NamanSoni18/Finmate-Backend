# agents/conversation_agent.py

from __future__ import annotations

from typing import Any, Dict, Optional

from agents.central_context_agent import CentralContextAgent
from agents.document_verification_agent import DocumentVerificationAgent
from agents.risk_assessment_agent import RiskAssessmentAgent
from agents.verification_agent import VerificationAgent
from agents.sanction_letter_generator import SanctionLetterGenerator
from agents.sentiment_analysis_agent import SentimentAnalysisAgent  # Add this import

class ConversationAgent:
    """Prototype conversation agent with sentiment analysis integration."""

    def __init__(self, context_agent: Optional[CentralContextAgent] = None):
        self.context_agent = context_agent or CentralContextAgent()
        self.verification_agent = VerificationAgent()
        self.risk_assessment_agent = RiskAssessmentAgent()
        self.document_verification_agent = DocumentVerificationAgent()
        self.sanction_generator = SanctionLetterGenerator()
        self.sentiment_agent = SentimentAnalysisAgent()  # Initialize the sentiment agent

    def handle_message(self, *, session_id: str, message: str) -> Dict[str, Any]:
        ctx = self.context_agent.get(session_id)
        text = (message or "").strip()
        
        # Analyze sentiment first
        sentiment_result = self.sentiment_agent.analyze_sentiment(text)
        self.context_agent.add_event(
            session_id, 
            kind="sentiment_analysis", 
            payload={"message": text, "sentiment": sentiment_result}
        )
        
        # Check for escalation based on sentiment
        if self.sentiment_agent.should_escalate(sentiment_result):
            response = self._handle_escalation(ctx, sentiment_result)
            return {
                "message": response,
                "meta": {"escalated": True, "sentiment": sentiment_result}
            }
        
        # Add emotional acknowledgment if needed
        emotional_acknowledgment = ""
        if sentiment_result.get("confidence", 0) > 0.5:
            emotional_acknowledgment = self.sentiment_agent.get_response_suggestion(sentiment_result)
            if emotional_acknowledgment:
                emotional_acknowledgment += " "

        if text.lower() in {"restart", "reset", "start over", "new"}:
            self.context_agent.update(session_id, state="AWAITING_PHONE", customer=None, loan_updates={})
            return {
                "message": f"{emotional_acknowledgment}Sure — let's start over. Please share your 10-digit mobile number.", 
                "meta": {"reset": True, "sentiment": sentiment_result}
            }

        if ctx.state == "AWAITING_PHONE":
            result = self.verification_agent.verify_customer(text)
            if result.get("status") == "success":
                self.context_agent.update(session_id, state="AWAITING_AMOUNT", customer=result)
                return {
                    "message": f"{emotional_acknowledgment}Thank you, {result.get('name')}! How much would you like to borrow?",
                    "meta": {"customerName": result.get("name"), "preApprovedLimit": result.get("pre_approved_limit"), "sentiment": sentiment_result},
                }
            return {
                "message": f"{emotional_acknowledgment}Please provide a valid 10-digit mobile number.", 
                "meta": {"sentiment": sentiment_result}
            }

        if ctx.state == "AWAITING_AMOUNT":
            try:
                amount = int("".join(ch for ch in text if ch.isdigit()))
            except Exception:
                amount = 0
            if amount <= 0:
                return {
                    "message": f"{emotional_acknowledgment}Please tell me the loan amount in numbers (e.g., 500000).", 
                    "meta": {"sentiment": sentiment_result}
                }
            self.context_agent.update(session_id, state="ASSESSING", loan_updates={"requested_amount": amount})

        if ctx.state == "ASSESSING":
            amount = int(ctx.loan.get("requested_amount") or 0)
            customer = ctx.customer or {}
            phone = customer.get("phone") or ""
            decision = self.risk_assessment_agent.assess(phone, amount)

            if decision.get("status") == "approved_instant":
                letter = self.sanction_generator.generate_letter(customer, {"approved_amount": amount, "interest_rate": "10.99%"})
                self.context_agent.update(session_id, state="DONE")
                if letter.get("status") == "success":
                    return {
                        "message": f"{emotional_acknowledgment}Approved! Sanction letter generated: {letter.get('filename')}", 
                        "meta": {"approved": True, "sentiment": sentiment_result}
                    }
                return {
                    "message": f"{emotional_acknowledgment}Approved, but failed to generate sanction letter.", 
                    "meta": {"approved": True, "sentiment": sentiment_result}
                }

            if decision.get("status") == "pending_salary_slip":
                self.context_agent.update(session_id, state="AWAITING_DOCUMENT", loan_updates={"requested_amount": amount})
                return {
                    "message": f"{emotional_acknowledgment}{decision.get('reason') or 'Please upload salary slip.'}", 
                    "meta": {"needsDocument": True, "sentiment": sentiment_result}
                }

            self.context_agent.update(session_id, state="DONE")
            return {
                "message": f"{emotional_acknowledgment}{decision.get('reason') or 'Unable to proceed.'}", 
                "meta": {"approved": False, "sentiment": sentiment_result}
            }

        if ctx.state == "AWAITING_DOCUMENT":
            customer = ctx.customer or {}
            phone = customer.get("phone") or ""
            amount = int(ctx.loan.get("requested_amount") or 0)
            doc = self.document_verification_agent.verify_salary_slip(phone, requested_amount=amount)
            if doc.get("status") == "verified":
                self.context_agent.update(session_id, state="ASSESSING")
                return {
                    "message": f"{emotional_acknowledgment}Document verified. Re-assessing your request...", 
                    "meta": {"documentVerified": True, "sentiment": sentiment_result}
                }
            self.context_agent.update(session_id, state="DONE")
            return {
                "message": f"{emotional_acknowledgment}{doc.get('message') or 'Document verification failed.'}", 
                "meta": {"documentVerified": False, "sentiment": sentiment_result}
            }

        return {
            "message": f"{emotional_acknowledgment}This session has ended. Type 'restart' to begin again.", 
            "meta": {"ended": True, "sentiment": sentiment_result}
        }
    
    def _handle_escalation(self, ctx, sentiment_result):
        """Handle escalation based on negative sentiment."""
        dominant_state = sentiment_result.get("dominant_state", "")
        
        if dominant_state == "negative":
            return "I understand your frustration. Let me connect you with a human agent who can better assist you. They will be with you shortly."
        elif dominant_state == "urgent":
            return "I understand this is urgent. Let me prioritize your request and connect you with a specialist immediately."
        else:
            return "I understand you need additional assistance. Let me connect you with a human agent who can help."