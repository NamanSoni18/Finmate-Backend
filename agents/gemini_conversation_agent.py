# agents/gemini_conversation_agent.py

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

import requests


class GeminiConversationAgent:
    """Gemini-backed conversational AI loan advisor.

    Goals:
    - Act as a knowledgeable financial advisor who educates and guides
    - Analyze customer profile and provide personalized recommendations
    - Keep conversations natural and engaging
    - Extract structured fields when present (loan amount + tenure months)

    This uses the Gemini REST API via `requests` (no extra dependency).

    Env vars:
    - GEMINI_API_KEY (required)
    - GEMINI_MODEL (optional, default: gemini-1.5-flash)
    """

    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        self.model = os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash"
        self.conversation_history = []

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def respond(
        self,
        *,
        user_message: str,
        state: str,
        customer: Optional[Dict[str, Any]] = None,
        loan_details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return JSON with assistant text and extracted fields.

        Returns dict with keys:
        - message: str
        - extracted: {amount: int|null, tenure_months: int|null, confidence: float}
        """

        loan_details = loan_details or {}
        known_amount = loan_details.get("requested_amount")
        known_tenure = loan_details.get("tenure")

        missing_amount = known_amount in (None, 0, "")
        missing_tenure = known_tenure in (None, 0, "")

        # State hint: ask for the field the backend is currently waiting for.
        if state == "AWAITING_TENURE":
            missing_amount = False
            missing_tenure = True
        elif state == "AWAITING_LOAN_AMOUNT":
            missing_amount = True

        fallback_message = ""
        if missing_amount and missing_tenure:
            fallback_message = "Could you please share the loan amount and tenure?"
        elif missing_amount:
            fallback_message = "Could you please share the loan amount you want? (e.g., '1.5 lakh' or '250000')"
        elif missing_tenure:
            fallback_message = "Could you please share the tenure? (e.g., '12 months' or '2 years')"

        if not self.api_key:
            return {
                "message": fallback_message,
                "extracted": {"amount": None, "tenure_months": None, "confidence": 0.0},
            }

        customer_name = (customer or {}).get("name")
        pre_limit = (customer or {}).get("pre_approved_limit")
        salary = (customer or {}).get("salary")
        credit_score = (customer or {}).get("credit_score")

        # Format customer insights properly
        pre_limit_str = f"₹{pre_limit:,}" if pre_limit else "Not yet known"
        salary_str = f"₹{salary:,}" if salary else "Not yet known"
        
        # Determine what we need
        if missing_amount and missing_tenure:
            needed = "loan amount and tenure"
        elif missing_amount:
            needed = "loan amount"
        elif missing_tenure:
            needed = "tenure"
        else:
            needed = "we have what we need"

        system_prompt = (
            "You are an AI-powered financial advisor for FinMate - friendly, knowledgeable, and genuinely helpful. "
            "Your role is to:\n"
            "1. EDUCATE: Explain loan concepts naturally (EMI, tenure, interest, credit scores) when relevant\n"
            "2. ANALYZE: Use customer's financial profile to give personalized insights\n"
            "3. GUIDE: Help them make informed decisions, not just collect data\n"
            "4. CONVERSE: Talk like a human advisor - warm, professional, and engaging\n\n"
            
            "PERSONALITY:\n"
            "- Use natural language, contractions, and conversational tone\n"
            "- Show empathy and understanding\n"
            "- Provide context and 'why' behind questions\n"
            "- Use emojis sparingly (1-2 max) to add warmth\n"
            "- Keep responses 2-4 sentences typically\n\n"
            
            "FINANCIAL KNOWLEDGE TO SHARE (when relevant):\n"
            "- EMI: Monthly payment calculated from loan amount, interest rate, and tenure\n"
            "- Tenure: Longer = lower EMI but more total interest; Shorter = higher EMI but less interest\n"
            "- Credit Score: 750+ is excellent; affects approval and interest rates\n"
            "- Pre-approved limit: Amount you can get instantly without extra documents\n"
            "- Interest Rate: Annual cost of borrowing (typically 10-14% for personal loans)\n\n"
            
            f"CURRENT CUSTOMER INSIGHTS:\n"
            f"- Name: {customer_name or 'Not yet known'}\n"
            f"- Pre-approved limit: {pre_limit_str}\n"
            f"- Monthly salary: {salary_str}\n"
            f"- Credit score: {credit_score or 'Not yet known'}\n\n"
            
            f"WHAT WE NEED NOW: {needed}\n\n"
            
            "Output MUST be valid JSON only:\n"
            "{\n"
            "  \"message\": \"Your conversational, helpful response\",\n"
            "  \"amount\": number or null,\n"
            "  \"tenure_months\": number or null,\n"
            "  \"confidence\": number between 0-1\n"
            "}\n\n"
            
            "EXTRACTION RULES:\n"
            "- Amount: '3 lakhs' => 300000, '2.5 lakh' => 250000, '₹3,00,000' => 300000\n"
            "- Tenure: '23 months' => 23, '2 years' => 24\n"
            "- Confidence >= 0.7 only when you're sure it's a specific amount/tenure (NOT a range)\n"
            "- If they give a range, set confidence < 0.5 and ask them to choose\n"
        )

        context_bits = {
            "state": state,
            "customer_name": customer_name,
            "pre_approved_limit": pre_limit,
            "known_loan_details": {
                "requested_amount": loan_details.get("requested_amount"),
                "tenure": loan_details.get("tenure"),
            },
        }

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": system_prompt},
                        {"text": f"Context: {json.dumps(context_bits)}"},
                        {"text": f"User: {user_message}"},
                    ],
                }
            ]
        }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        try:
            res = requests.post(url, json=payload, timeout=10)
            res.raise_for_status()
            data = res.json()

            text = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            parsed = _extract_json_object(text)
            if not isinstance(parsed, dict):
                return {
                    "message": fallback_message,
                    "extracted": {"amount": None, "tenure_months": None, "confidence": 0.0},
                }

            amount = parsed.get("amount")
            tenure_months = parsed.get("tenure_months")
            confidence = parsed.get("confidence")
            message = parsed.get("message") or ""

            return {
                "message": str(message),
                "extracted": {
                    "amount": int(amount) if isinstance(amount, (int, float)) else None,
                    "tenure_months": int(tenure_months)
                    if isinstance(tenure_months, (int, float))
                    else None,
                    "confidence": float(confidence) if isinstance(confidence, (int, float)) else 0.0,
                },
            }
        except Exception:
            return {
                "message": fallback_message,
                "extracted": {"amount": None, "tenure_months": None, "confidence": 0.0},
            }

    def generate_contextual_message(
        self,
        *,
        context_type: str,
        customer: Optional[Dict[str, Any]] = None,
        loan_details: Optional[Dict[str, Any]] = None,
        extra_context: Optional[str] = None,
    ) -> str:
        """Generate natural, personalized messages for different contexts.
        
        context_type options:
        - 'welcome_after_verification': After finding customer profile
        - 'processing': While evaluating loan
        - 'explaining_approval': After approval
        - 'explaining_rejection': After rejection
        - 'asking_for_clarity': When need clarification
        """
        
        if not self.api_key:
            return self._fallback_message(context_type, customer, loan_details)

        customer_name = (customer or {}).get("name", "there")
        pre_limit = (customer or {}).get("pre_approved_limit")
        salary = (customer or {}).get("salary")
        requested_amount = (loan_details or {}).get("requested_amount")
        tenure = (loan_details or {}).get("tenure")

        # Format values with proper handling of None
        salary_str = f"₹{salary:,}" if salary else "unknown"
        pre_limit_str = f"₹{pre_limit:,}" if pre_limit else "unknown"
        amount_str = f"₹{requested_amount:,}" if requested_amount else "unknown"
        tenure_str = f"{tenure} months" if tenure else "unknown"

        prompt = (
            f"You are a friendly AI financial advisor for FinMate. Generate a natural, conversational message for this situation:\n\n"
            f"Context: {context_type}\n"
            f"Customer: {customer_name}, Salary: {salary_str}, Pre-approved: {pre_limit_str}\n"
            f"Loan: Amount: {amount_str}, Tenure: {tenure_str}\n"
            f"Extra info: {extra_context or 'none'}\n\n"
            f"Guidelines:\n"
            f"- Be warm and professional\n"
            f"- 2-3 sentences max\n"
            f"- If educating, explain concepts simply\n"
            f"- Show genuine interest in helping\n"
            f"- Use the customer's name naturally\n\n"
            f"Return ONLY the message text, no JSON, no formatting."
        )

        try:
            res = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}",
                json={"contents": [{"role": "user", "parts": [{"text": prompt}]}]},
                timeout=8,
            )
            res.raise_for_status()
            data = res.json()
            text = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            ).strip()
            return text if text else self._fallback_message(context_type, customer, loan_details)
        except Exception:
            return self._fallback_message(context_type, customer, loan_details)

    def _fallback_message(
        self,
        context_type: str,
        customer: Optional[Dict[str, Any]],
        loan_details: Optional[Dict[str, Any]],
    ) -> str:
        """Fallback messages when Gemini is unavailable."""
        customer_name = (customer or {}).get("name", "there")
        pre_limit = (customer or {}).get("pre_approved_limit")
        known_amt = (loan_details or {}).get("requested_amount")
        
        # Format values safely
        pre_limit_str = f"₹{pre_limit:,}" if pre_limit else "₹500,000"
        known_amt_str = f"₹{known_amt:,}" if known_amt else "the loan"
        
        fallbacks = {
            "welcome_after_verification": f"Hello {customer_name}! 👋 Great to see you. You're pre-approved for up to {pre_limit_str}, which means instant approval for amounts within this limit. What amount would you like to borrow today?",
            "processing": f"Perfect, {customer_name}! I'm analyzing your loan application now. This will just take a moment...",
            "asking_for_clarity": "I want to make sure I understand your needs correctly. Could you help me clarify?",
            "asking_tenure_with_education": f"Great! For your {known_amt_str} loan, what repayment period would you prefer? Common options are 12, 24, or 36 months. Longer tenure means lower monthly EMI but more total interest.",
            "comparing_tenure_options": f"Good question! Let me help you compare. For {known_amt_str}: shorter tenure means higher monthly payments but you save on interest. Longer tenure gives you breathing room with lower EMIs but costs more overall. Which fits your budget better?",
            "explaining_tenure_concept": "No worries! Tenure is just how many months you want to repay the loan. Think of it like this: 12 months = higher monthly payment, done faster. 36 months = lower monthly payment, takes longer. What sounds manageable for you?",
            "redirect_to_tenure": f"Got it, I have your amount as {known_amt_str}. Now I just need to know the repayment period - would you prefer 12, 24, or 36 months?",
            "asking_for_tenure": f"Could you tell me how many months you'd like for repaying {known_amt_str}? You can say '12 months', '2 years', or just a number like '24'.",
            "responding_to_small_talk_need_amount": f"Hey {customer_name}! 😊 I'm here to help you get the loan you need. You're pre-approved for up to {pre_limit_str}. What amount would you like to borrow? You can tell me like '2 lakhs' or '250000'.",
            "choosing_between_two_amounts": "I see you have two amounts in mind. Both are good options - which one would work better for your needs?",
            "exploring_loan_range": f"That's a good range to consider, {customer_name}! With your pre-approval of {pre_limit_str}, you have flexibility. Which amount would you like to see the EMI breakdown for first?",
            "loan_preview_confirmation": f"Here's your loan summary: {known_amt_str} for the tenure you selected. This looks good! Would you like to proceed with this, or would you like to adjust anything?",
            "asking_what_to_change": f"No problem, {customer_name}! What would you like to adjust - the loan amount or the repayment tenure? Just let me know and I'll recalculate everything for you.",
            "clarifying_confirmation": "Just to confirm - would you like to proceed with this loan as shown, or would you prefer to make any changes to the amount or tenure?",
        }
        return fallbacks.get(context_type, f"I'm here to help you with your loan, {customer_name}. Could you tell me more about what you need?")


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None

    # Common failure mode: model wraps JSON in markdown or adds extra text.
    # Pull the first {...} block.
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None

    candidate = m.group(0)
    try:
        return json.loads(candidate)
    except Exception:
        return None
