# api_server.py
"""Flask JSON API wrapper around the loan_chatbot Python agents.

This is the backend consumed by the Next.js proxy route (POST /api/loan-chatbot).
We intentionally do NOT serve the legacy HTML UI here.

Run locally:
  cd loan_chatbot/loan_chatbot
  python api_server.py
"""

from __future__ import annotations

from flask import Flask, jsonify, request
from flask_cors import CORS

import math
import os
import re
import sys
import time
import uuid
from typing import Any, Dict, Optional


# Ensure we can import `agents/*` and `utils/*` regardless of cwd
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from agents.master_agent import MasterAgent
from agents.gemini_conversation_agent import GeminiConversationAgent
from utils.database import customer_db


app = Flask(__name__)
CORS(app)

master_agent = MasterAgent()
gemini_agent = GeminiConversationAgent()

# Simple in-memory session store.
# NOTE: In production you'd use Redis/DB and proper auth.
_sessions: Dict[str, Dict[str, Any]] = {}


def _get_gemini_confidence_threshold() -> float:
    raw = (os.environ.get("GEMINI_CONFIDENCE_THRESHOLD") or "0.7").strip()
    try:
        v = float(raw)
        if v < 0:
            return 0.0
        if v > 1:
            return 1.0
        return v
    except ValueError:
        return 0.7


def _maybe_start_underwriting_after_tenure(
    *,
    session: Dict[str, Any],
    customer_details: Optional[Dict[str, Any]],
    loan_details: Dict[str, Any],
    pending: Dict[str, Any],
    meta: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if not customer_details:
        session["state"] = "AWAITING_PHONE"
        return {
            "message": "Let's restart. Please provide your 10-digit mobile number to get started.",
            "meta": {"reset": True},
        }

    sales_result = master_agent.sales_agent.discuss_loan(
        customer_details["phone"],
        loan_details["requested_amount"],
        loan_details["tenure"],
    )

    if sales_result.get("status") == "suggestion":
        pending["suggested_amount"] = int(sales_result.get("suggested_amount") or 0)
        pending["requested_amount"] = int(loan_details.get("requested_amount") or 0)
        session["pending"] = pending
        session["state"] = "AWAITING_SUGGESTION_CONFIRM"

        response_message = (sales_result.get("message") or "")
        response_message += (
            "\n\nWhat would you like to do?\n\n"
            "💚 Reply 'yes' for instant approval with the suggested amount\n"
            "📄 Reply 'no' to apply for your requested amount (may need document verification)"
        )
        return {"message": response_message, "meta": meta}

    if sales_result.get("status") == "confirmed":
        loan_details["final_amount"] = sales_result.get("final_amount")
        session["loan_details"] = loan_details
        session["state"] = "UNDERWRITING_RUNNING"
        return None

    response_message = sales_result.get("message") or "I couldn't process your request right now."
    session["state"] = "CONVERSATION_END"
    return {"message": response_message, "meta": {"ended": True}}


def _compute_emi(principal: int, annual_rate_percent: float, tenure_months: int) -> int:
    """Compute monthly EMI using standard amortization formula."""
    if principal <= 0 or tenure_months <= 0:
        return 0

    monthly_rate = (annual_rate_percent / 100.0) / 12.0
    if monthly_rate <= 0:
        return int(math.ceil(principal / tenure_months))

    factor = (1 + monthly_rate) ** tenure_months
    emi = principal * monthly_rate * factor / (factor - 1)
    return int(round(emi))


def _extract_amount(text: str) -> Optional[int]:
    """Extract a loan amount from free-form text.

    Supports:
    - "500000", "5,00,000", "₹500000"
    - "2 lakh", "2.5 lakhs", "1 crore"
    """
    if not text:
        return None

    raw = text.strip().lower()

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


def _extract_amount_candidates(text: str) -> list[int]:
    if not text:
        return []

    raw = text.strip().lower()
    candidates: list[int] = []

    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(lakh|lakhs|lac|lacs)", raw):
        try:
            candidates.append(int(float(m.group(1)) * 100_000))
        except Exception:
            pass

    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(crore|crores)", raw):
        try:
            candidates.append(int(float(m.group(1)) * 10_000_000))
        except Exception:
            pass

    for m in re.finditer(r"(?:₹|rs\.?\s*)?(\d[\d,]{2,})", raw):
        try:
            digits = m.group(1).replace(",", "")
            # Heuristic: avoid treating a 10-digit mobile number as an amount
            if len(digits) == 10 and digits[0] in {"6", "7", "8", "9"}:
                continue
            candidates.append(int(digits))
        except Exception:
            pass

    uniq: list[int] = []
    seen: set[int] = set()
    for v in candidates:
        if v > 0 and v not in seen:
            uniq.append(v)
            seen.add(v)
    return uniq


def _is_range_expression(text: str) -> bool:
    """Detect if user is providing a range instead of a specific amount."""
    if not text:
        return False
    
    raw = text.lower()
    
    # Check for explicit range keywords
    range_patterns = [
        r"between\s+.*\s+(and|to|or)",
        r"range\s+(from|between|of)",
        r"\d+\s*-\s*\d+\s*(lakh|lakhs|crore)",
        r"(from|around)\s+\d.*to\s+\d",
    ]
    
    for pattern in range_patterns:
        if re.search(pattern, raw):
            return True
    
    # Check if multiple amounts are mentioned
    amount_candidates = _extract_amount_candidates(text)
    return len(amount_candidates) >= 2


def _extract_tenure_months(text: str) -> Optional[int]:
    """Extract tenure in months from free-form text.

    Supports:
    - "12", "12 months"
    - "1 year", "2 years" (converted to months)
    """
    if not text:
        return None

    raw = text.strip().lower()

    y = re.search(r"(\d+)\s*(year|years|yr|yrs)", raw)
    if y:
        return int(y.group(1)) * 12

    m = re.search(r"\b(\d+)\s*(month|months|mo|mos)\b", raw)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None

    # Accept plain integers only when the message is essentially just a number
    raw_no_space = re.sub(r"\s+", "", raw)
    if re.fullmatch(r"\d+", raw_no_space):
        try:
            return int(raw_no_space)
        except ValueError:
            return None

    return None


def _get_sentiment_states(message: str) -> set[str]:
    try:
        result = master_agent.sentiment_agent.analyze_sentiment(message or "")
        states = result.get("detected_states") or []
        return {str(s).lower() for s in states}
    except Exception:
        return set()


def _is_yes(text: str) -> bool:
    t = (text or "").strip().lower()
    return (
        t in {"yes", "y", "yeah", "yep", "ok", "okay", "sure", "proceed", "go ahead"}
        or "yes" in t
    )


def _is_no(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in {"no", "n", "nope", "nah", "don't", "do not", "decline"} or t.startswith("no")


def _reset_session(session: Dict[str, Any]) -> None:
    session["state"] = "AWAITING_PHONE"
    session["customer_details"] = None
    session["loan_details"] = {}
    session["pending"] = {}


def _show_emi_preview_and_confirm(
    session: Dict[str, Any],
    customer_details: Dict[str, Any],
    loan_details: Dict[str, Any],
    gemini_agent: Any,
) -> Dict[str, Any]:
    """Show EMI breakdown and ask user to confirm before processing."""
    amount = int(loan_details.get("requested_amount", 0))
    tenure = int(loan_details.get("tenure", 0))
    annual_rate = 10.99
    
    emi = _compute_emi(amount, annual_rate, tenure)
    total_payment = emi * tenure
    total_interest = total_payment - amount
    
    # Use AI to present options and ask for confirmation
    if gemini_agent.is_configured():
        salary = customer_details.get("salary", 0)
        emi_to_salary_ratio = (emi / salary * 100) if salary > 0 else 0
        
        context = (
            f"Show loan preview: ₹{amount:,} for {tenure} months. "
            f"EMI: ₹{emi:,}/month ({emi_to_salary_ratio:.1f}% of ₹{salary:,} salary). "
            f"Total interest: ₹{total_interest:,}. Total payment: ₹{total_payment:,}. "
            f"Ask if they want to proceed with this, or if they'd like to adjust the amount or tenure. Be encouraging but let them decide."
        )
        
        ai_message = gemini_agent.generate_contextual_message(
            context_type="loan_preview_confirmation",
            customer=customer_details,
            loan_details={"requested_amount": amount, "tenure": tenure, "emi": emi, "total_interest": total_interest},
            extra_context=context
        )
    else:
        ai_message = (
            f"📊 Here's what your loan would look like:\n\n"
            f"💰 Loan Amount: ₹{amount:,}\n"
            f"📅 Tenure: {tenure} months\n"
            f"💳 Monthly EMI: ₹{emi:,}\n"
            f"📈 Total Interest: ₹{total_interest:,}\n"
            f"💵 Total Payment: ₹{total_payment:,}\n\n"
            f"Would you like to proceed with this? Say 'yes' to continue, or you can change the amount or tenure if you'd like."
        )
    
    return {"message": ai_message, "meta": {}}


def _show_emi_preview_and_confirm(
    session: Dict[str, Any],
    customer_details: Dict[str, Any],
    loan_details: Dict[str, Any],
    gemini_agent: Any,
) -> Dict[str, Any]:
    """Show EMI breakdown and ask user to confirm before processing."""
    amount = int(loan_details.get("requested_amount", 0))
    tenure = int(loan_details.get("tenure", 0))
    annual_rate = 10.99
    
    emi = _compute_emi(amount, annual_rate, tenure)
    total_payment = emi * tenure
    total_interest = total_payment - amount
    
    # Use AI to present options and ask for confirmation
    if gemini_agent.is_configured():
        salary = customer_details.get("salary", 0)
        emi_to_salary_ratio = (emi / salary * 100) if salary > 0 else 0
        
        context = (
            f"Show loan preview: ₹{amount:,} for {tenure} months. "
            f"EMI: ₹{emi:,}/month ({emi_to_salary_ratio:.1f}% of ₹{salary:,} salary). "
            f"Total interest: ₹{total_interest:,}. Total payment: ₹{total_payment:,}. "
            f"Ask if they want to proceed with this, or if they'd like to adjust the amount or tenure. Be encouraging but let them decide."
        )
        
        ai_message = gemini_agent.generate_contextual_message(
            context_type="loan_preview_confirmation",
            customer=customer_details,
            loan_details={"requested_amount": amount, "tenure": tenure, "emi": emi, "total_interest": total_interest},
            extra_context=context
        )
    else:
        ai_message = (
            f"📊 Here's what your loan would look like:\n\n"
            f"💰 Loan Amount: ₹{amount:,}\n"
            f"📅 Tenure: {tenure} months\n"
            f"💳 Monthly EMI: ₹{emi:,}\n"
            f"📈 Total Interest: ₹{total_interest:,}\n"
            f"💵 Total Payment: ₹{total_payment:,}\n\n"
            f"Would you like to proceed with this? Say 'yes' to continue, or you can change the amount or tenure if you'd like."
        )
    
    return {"message": ai_message, "meta": {}}


def _get_or_create_session(session_id: Optional[str]) -> Dict[str, Any]:
    if session_id and session_id in _sessions:
        _sessions[session_id]["last_seen"] = time.time()
        return _sessions[session_id]

    new_id = session_id or uuid.uuid4().hex
    _sessions[new_id] = {
        "id": new_id,
        "state": "AWAITING_PHONE",
        "customer_details": None,
        "loan_details": {},
        "pending": {},
        "last_seen": time.time(),
    }
    return _sessions[new_id]


def _process_message(session: Dict[str, Any], user_message: str) -> Dict[str, Any]:
    user_message = (user_message or "").strip()
    gemini_threshold = _get_gemini_confidence_threshold()
    sentiment_states = _get_sentiment_states(user_message)

    # Global commands
    if user_message.lower() in {"restart", "reset", "start over", "new", "new chat"}:
        _reset_session(session)
        return {
            "message": "Sure — let's start over. Please share your 10-digit mobile number.",
            "meta": {"reset": True},
        }

    if user_message.lower() in {"help", "what can you do", "menu"}:
        return {
            "message": "I can help you check eligibility, discuss loan amounts/tenure, and generate a sanction letter. To begin, share your 10-digit mobile number.",
            "meta": {},
        }

    state = session["state"]
    customer_details = session.get("customer_details")
    loan_details = session.get("loan_details") or {}
    pending = session.get("pending") or {}

    meta: Dict[str, Any] = {}
    response_message = ""

    if state == "AWAITING_PHONE":
        phone_match = re.search(r"\b\d{10}\b", user_message)
        phone = phone_match.group(0) if phone_match else None

        if phone:
            verification_result = master_agent.verification_agent.verify_customer(user_message)
            if verification_result.get("status") == "success":
                session["customer_details"] = verification_result
                session["state"] = "AWAITING_LOAN_AMOUNT"
                customer_details = verification_result

                pre_approved_limit = verification_result.get("pre_approved_limit")
                
                # Generate personalized welcome using AI
                if gemini_agent.is_configured():
                    response_message = gemini_agent.generate_contextual_message(
                        context_type="welcome_after_verification",
                        customer=customer_details,
                        extra_context=f"Explain what pre-approved limit means and why it's beneficial. Credit score: {customer_details.get('credit_score')}"
                    )
                else:
                    response_message = (
                        f"Hello {customer_details.get('name')}! 👋 Great to see you.\n\n"
                        f"Good news! You're pre-approved for up to ₹{pre_approved_limit:,}. "
                        "This means you can get instant approval for loans within this limit!\n\n"
                        "What amount would you like to borrow today?"
                    )

                meta.update(
                    {
                        "showPreApprovalBanner": True,
                        "customerName": customer_details.get("name"),
                        "preApprovedLimit": pre_approved_limit,
                    }
                )

                return {"message": response_message, "meta": meta}

            response_message = (
                "I'm sorry, but I couldn't find an account associated with that number. Please check and try again."
            )
        else:
            response_message = "To get started, please share your 10-digit mobile number so I can check your eligibility."

    elif state == "AWAITING_LOAN_AMOUNT":
        raw_lower = user_message.lower()
        
        # Handle general conversational messages when waiting for amount
        small_talk_keywords = ["hey", "hello", "hi", "confused", "help", "don't know", "not sure"]
        is_small_talk = (
            len(user_message.split()) <= 3 and 
            any(keyword in raw_lower for keyword in small_talk_keywords)
        )
        
        if is_small_talk and gemini_agent.is_configured():
            pre_limit = (customer_details or {}).get("pre_approved_limit", 0)
            ai_response = gemini_agent.generate_contextual_message(
                context_type="responding_to_small_talk_need_amount",
                customer=customer_details,
                extra_context=f"User said '{user_message}' when asked for amount. Respond warmly, acknowledge their concern if any, then guide to share amount. Pre-limit: ₹{pre_limit:,}."
            )
            return {"message": ai_response, "meta": {}}
        
        amount_candidates = _extract_amount_candidates(user_message)
        if len(amount_candidates) >= 2 and (" or " in raw_lower or "/" in raw_lower):
            a = amount_candidates[0]
            b = amount_candidates[1]
            session["state"] = "AWAITING_LOAN_AMOUNT"
            
            if gemini_agent.is_configured():
                ai_response = gemini_agent.generate_contextual_message(
                    context_type="choosing_between_two_amounts",
                    customer=customer_details,
                    loan_details={"options": [a, b]},
                    extra_context=f"User gave two options: ₹{a:,} or ₹{b:,}. Ask which one they prefer, briefly explain implications if helpful."
                )
                return {"message": ai_response, "meta": {}}
            
            return {
                "message": f"I see two options: ₹{a:,} or ₹{b:,}. Which amount would you like to proceed with?",
                "meta": {},
            }

        amount = _extract_amount(user_message)
        extracted_tenure: Optional[int] = None

        if amount is None and gemini_agent.is_configured():
            gemini = gemini_agent.respond(
                user_message=user_message,
                state=state,
                customer=customer_details,
                loan_details=loan_details,
            )
            extracted = gemini.get("extracted") or {}
            confidence = float(extracted.get("confidence") or 0.0)

            if confidence >= gemini_threshold:
                gemini_amount = extracted.get("amount")
                gemini_tenure = extracted.get("tenure_months")
                if isinstance(gemini_amount, int):
                    amount = gemini_amount
                if isinstance(gemini_tenure, int):
                    extracted_tenure = gemini_tenure

            if amount is None:
                response_message = (gemini.get("message") or "").strip() or (
                    "Sure — what loan amount are you looking for? (You can type like '5 lakh' or '₹500000')"
                )
            else:
                if (gemini.get("message") or "").strip():
                    response_message = (gemini.get("message") or "").strip()

        if amount is None and "confused" in sentiment_states:
            pre_limit = None
            try:
                pre_limit = int((customer_details or {}).get("pre_approved_limit") or 0)
            except Exception:
                pre_limit = None

            if pre_limit and pre_limit > 0:
                response_message = (
                    f"No worries — I’ll make it simple. Your pre-approved limit is ₹{pre_limit:,}. "
                    "Tell me the amount you want (example: '1.5 lakh' or '250000')."
                )
            else:
                response_message = (
                    "No worries — just tell me the loan amount you want (example: '1.5 lakh' or '250000')."
                )

        if amount is not None:
            # Store the amount but don't lock it - just acknowledge and move to tenure
            loan_details["requested_amount"] = amount
            session["loan_details"] = loan_details

            if extracted_tenure is not None:
                loan_details["tenure"] = extracted_tenure
                session["loan_details"] = loan_details
                # Don't go to underwriting yet - go to confirmation first
                session["state"] = "AWAITING_CONFIRMATION"
                return _show_emi_preview_and_confirm(session, customer_details, loan_details, gemini_agent)
            else:
                session["state"] = "AWAITING_TENURE"
                if not response_message:
                    # AI-generated response explaining tenure with education
                    if gemini_agent.is_configured():
                        pre_limit = (customer_details or {}).get("pre_approved_limit", 0)
                        salary = (customer_details or {}).get("salary", 0)
                        annual_rate = 10.99
                        
                        # Calculate EMIs for common tenures to help user decide
                        emi_12 = _compute_emi(amount, annual_rate, 12)
                        emi_24 = _compute_emi(amount, annual_rate, 24)
                        emi_36 = _compute_emi(amount, annual_rate, 36)
                        
                        context_extra = (
                            f"Amount: ₹{amount:,}. Pre-limit: ₹{pre_limit:,}. Salary: ₹{salary:,}. "
                            f"Show EMI options: 12mo=₹{emi_12:,}, 24mo=₹{emi_24:,}, 36mo=₹{emi_36:,}. "
                            f"Explain trade-offs and help them choose based on their ₹{salary:,} salary."
                        )
                        
                        response_message = gemini_agent.generate_contextual_message(
                            context_type="asking_tenure_with_education",
                            customer=customer_details,
                            loan_details={"requested_amount": amount},
                            extra_context=context_extra
                        )
                    else:
                        response_message = f"Perfect! You're requesting ₹{amount:,}. Now, what repayment tenure would work for you? Common options are 12, 24, or 36 months."
        else:
            if not response_message:
                pre_limit = None
                try:
                    pre_limit = int((customer_details or {}).get("pre_approved_limit") or 0)
                except Exception:
                    pass
                
                if pre_limit and pre_limit > 0:
                    response_message = (
                        f"Great! Your pre-approved limit is ₹{pre_limit:,}. "
                        "What amount would you like to borrow? You can tell me like '2 lakhs' or '₹250000'."
                    )
                else:
                    response_message = "What loan amount are you looking for? You can tell me like '2 lakhs' or '₹250000'."

    elif state == "AWAITING_TENURE":
        # Detect if user is asking for comparison/advice ("which is better", "what should I choose", etc.)
        comparison_keywords = ["which", "better", "should i", "recommend", "suggest", "compare", "difference", "best"]
        is_asking_comparison = any(keyword in user_message.lower() for keyword in comparison_keywords)
        
        if is_asking_comparison and gemini_agent.is_configured():
            # Extract the tenure options they're comparing
            tenure_candidates = []
            for match in re.finditer(r"(\d+)\s*(month|year)", user_message.lower()):
                num = int(match.group(1))
                unit = match.group(2)
                months = num * 12 if "year" in unit else num
                tenure_candidates.append(months)
            
            # Use AI to compare and educate
            known_amt = loan_details.get("requested_amount", 0)
            salary = (customer_details or {}).get("salary", 0)
            
            annual_rate = 10.99
            emi_comparisons = []
            for t in tenure_candidates:
                if t > 0:
                    emi = _compute_emi(int(known_amt), annual_rate, t)
                    total_interest = (emi * t) - known_amt
                    emi_comparisons.append(f"{t} months: EMI ₹{emi:,}/month, Total Interest ₹{total_interest:,}")
            
            comparison_context = (
                f"User is comparing tenure options for ₹{known_amt:,} loan. "
                f"Options mentioned: {', '.join(str(t) for t in tenure_candidates)}. "
                f"EMI breakdown: {' vs '.join(emi_comparisons)}. "
                f"User salary: ₹{salary:,}. Explain trade-offs, recommend based on their salary, and ask which they prefer."
            )
            
            ai_response = gemini_agent.generate_contextual_message(
                context_type="comparing_tenure_options",
                customer=customer_details,
                loan_details=loan_details,
                extra_context=comparison_context
            )
            return {"message": ai_response, "meta": meta}
        
        # If user repeats an amount here, guide them back to tenure
        if _extract_amount(user_message) is not None and _extract_tenure_months(user_message) is None:
            known_amt = loan_details.get("requested_amount")
            if isinstance(known_amt, int) and known_amt > 0:
                if gemini_agent.is_configured():
                    ai_msg = gemini_agent.generate_contextual_message(
                        context_type="redirect_to_tenure",
                        customer=customer_details,
                        loan_details={"requested_amount": known_amt},
                        extra_context="User mentioned amount again. Gently redirect to tenure question."
                    )
                    return {"message": ai_msg, "meta": meta}
                return {
                    "message": f"Thanks! I've noted your loan amount as ₹{known_amt:,}. Now, how many months would you like for repayment? Popular choices are 12, 24, or 36 months.",
                    "meta": meta,
                }

        if "confused" in sentiment_states:
            known_amt = loan_details.get("requested_amount")
            if gemini_agent.is_configured():
                ai_msg = gemini_agent.generate_contextual_message(
                    context_type="explaining_tenure_concept",
                    customer=customer_details,
                    loan_details={"requested_amount": known_amt},
                    extra_context=f"User is confused about tenure. Explain concept simply with examples showing EMI calculations for ₹{known_amt:,} at different tenures (12, 24, 36 months). Make it relatable to their ₹{(customer_details or {}).get('salary', 0):,} salary."
                )
                return {"message": ai_msg, "meta": meta}
            
            amt_hint = f" for your ₹{int(known_amt):,} loan" if isinstance(known_amt, int) and known_amt > 0 else ""
            return {
                "message": (
                    f"No worries! Tenure is simply how many months you'd like to repay the loan{amt_hint}. "
                    "\n\nLonger tenure = Lower monthly EMI but more interest overall. "
                    "Shorter tenure = Higher EMI but less total interest. "
                    "\n\nCommon options are 12, 24, or 36 months. What works for you?"
                ),
                "meta": meta,
            }

        tenure = _extract_tenure_months(user_message)
        if tenure is None and gemini_agent.is_configured():
            gemini = gemini_agent.respond(
                user_message=user_message,
                state=state,
                customer=customer_details,
                loan_details=loan_details,
            )
            extracted = gemini.get("extracted") or {}
            confidence = float(extracted.get("confidence") or 0.0)
            if confidence >= gemini_threshold and isinstance(extracted.get("tenure_months"), int):
                tenure = extracted.get("tenure_months")
            else:
                msg = (gemini.get("message") or "").strip()
                if msg:
                    return {"message": msg, "meta": meta}

        if tenure is None:
            known_amt = loan_details.get("requested_amount")
            if gemini_agent.is_configured():
                ai_msg = gemini_agent.generate_contextual_message(
                    context_type="asking_for_tenure",
                    customer=customer_details,
                    loan_details={"requested_amount": known_amt},
                    extra_context=f"Didn't understand tenure from: '{user_message}'. Ask again in a friendly, educational way. Provide examples."
                )
                return {"message": ai_msg, "meta": meta}
            
            if isinstance(known_amt, int) and known_amt > 0:
                return {
                    "message": f"Could you tell me the tenure for your ₹{known_amt:,} loan? For example, '12 months', '2 years', or just '24'.",
                    "meta": meta
                }
            return {"message": "Could you tell me the repayment tenure? For example, '12 months', '2 years', or just '24'.", "meta": meta}

        loan_details["tenure"] = tenure
        session["loan_details"] = loan_details
        
        # Don't lock in - show EMI preview and ask for confirmation first
        session["state"] = "AWAITING_CONFIRMATION"
        return _show_emi_preview_and_confirm(session, customer_details, loan_details, gemini_agent)

    if session["state"] == "AWAITING_CONFIRMATION":
        # User can confirm, change amount, or change tenure
        if _is_yes(user_message) or "proceed" in user_message.lower() or "confirm" in user_message.lower():
            # User confirmed - proceed to underwriting
            maybe = _maybe_start_underwriting_after_tenure(
                session=session,
                customer_details=customer_details,
                loan_details=loan_details,
                pending=pending,
                meta=meta,
            )
            if maybe is not None:
                return maybe
        elif _is_no(user_message) or "change" in user_message.lower() or "different" in user_message.lower():
            # User wants to change - ask what they want to adjust
            if gemini_agent.is_configured():
                current_amt = loan_details.get("requested_amount", 0)
                current_tenure = loan_details.get("tenure", 0)
                ai_msg = gemini_agent.generate_contextual_message(
                    context_type="asking_what_to_change",
                    customer=customer_details,
                    loan_details=loan_details,
                    extra_context=f"User said '{user_message}' after seeing EMI preview for ₹{current_amt:,} @ {current_tenure} months. Ask what they'd like to adjust - amount or tenure?"
                )
                session["state"] = "AWAITING_LOAN_AMOUNT"  # Reset to let them change
                return {"message": ai_msg, "meta": {}}
            else:
                session["state"] = "AWAITING_LOAN_AMOUNT"
                return {"message": "No problem! What would you like to change? Tell me a new amount or tenure and I'll recalculate for you.", "meta": {}}
        else:
            # Check if they mentioned a new amount or tenure
            new_amount = _extract_amount(user_message)
            new_tenure = _extract_tenure_months(user_message)
            
            if new_amount is not None:
                loan_details["requested_amount"] = new_amount
                session["loan_details"] = loan_details
                if new_tenure is not None:
                    loan_details["tenure"] = new_tenure
                    session["loan_details"] = loan_details
                    return _show_emi_preview_and_confirm(session, customer_details, loan_details, gemini_agent)
                else:
                    session["state"] = "AWAITING_TENURE"
                    if gemini_agent.is_configured():
                        ai_msg = gemini_agent.generate_contextual_message(
                            context_type="asking_tenure_with_education",
                            customer=customer_details,
                            loan_details={"requested_amount": new_amount},
                            extra_context=f"User changed amount to ₹{new_amount:,}. Now need tenure. Show EMI examples for different tenures."
                        )
                        return {"message": ai_msg, "meta": {}}
                    return {"message": f"Got it! For ₹{new_amount:,}, what tenure would you like?", "meta": {}}
            elif new_tenure is not None:
                loan_details["tenure"] = new_tenure
                session["loan_details"] = loan_details
                return _show_emi_preview_and_confirm(session, customer_details, loan_details, gemini_agent)
            else:
                # User said something unclear - use AI to respond
                if gemini_agent.is_configured():
                    current_amt = loan_details.get("requested_amount", 0)
                    current_tenure = loan_details.get("tenure", 0)
                    ai_msg = gemini_agent.generate_contextual_message(
                        context_type="clarifying_confirmation",
                        customer=customer_details,
                        loan_details=loan_details,
                        extra_context=f"User said '{user_message}' when asked to confirm ₹{current_amt:,} @ {current_tenure} months. Clarify if they want to proceed or change something."
                    )
                    return {"message": ai_msg, "meta": {}}
                return {"message": "Would you like to proceed with this loan, or would you like to adjust the amount or tenure?", "meta": {}}

    if session["state"] == "AWAITING_SUGGESTION_CONFIRM":
        if not customer_details:
            session["state"] = "AWAITING_PHONE"
            return {"message": "Let's restart — please share your 10-digit mobile number.", "meta": {"reset": True}}

        suggested_amount = int((pending.get("suggested_amount") or 0))
        requested_amount = int((pending.get("requested_amount") or 0))

        if _is_yes(user_message):
            loan_details["final_amount"] = suggested_amount
            if gemini_agent.is_configured():
                response_message = gemini_agent.generate_contextual_message(
                    context_type="processing",
                    customer=customer_details,
                    loan_details={"requested_amount": suggested_amount, "tenure": loan_details.get("tenure")},
                    extra_context="Processing instant approval amount. Be encouraging and explain what happens next."
                )
            else:
                response_message = f"Great! I'm processing your loan application for ₹{suggested_amount:,}. One moment please..."
        elif _is_no(user_message):
            loan_details["final_amount"] = requested_amount
            if gemini_agent.is_configured():
                response_message = gemini_agent.generate_contextual_message(
                    context_type="processing",
                    customer=customer_details,
                    loan_details={"requested_amount": requested_amount, "tenure": loan_details.get("tenure")},
                    extra_context="Processing higher amount that needs document verification. Explain this briefly and positively."
                )
            else:
                response_message = f"Understood. I'll process your application for ₹{requested_amount:,}. This may require additional documentation. Processing now..."
        else:
            return {
                "message": "I need your confirmation to proceed. Would you like to:\n\n✅ Say 'yes' for instant approval with the suggested amount\n❌ Say 'no' to apply for your requested amount (may need extra documents)",
                "meta": {},
            }

        session["loan_details"] = loan_details
        session["state"] = "UNDERWRITING_RUNNING"

    if session["state"] == "UNDERWRITING_RUNNING":
        tenure = int(loan_details.get("tenure") or 0)
        final_amount = int(loan_details.get("final_amount") or 0)

        underwriting_result = master_agent.underwriting_agent.evaluate_loan(customer_details["phone"], final_amount)

        if underwriting_result.get("status") == "approved_instant":
            approved_amount = underwriting_result.get("approved_amount")
            annual_rate = 10.99
            emi = _compute_emi(int(approved_amount), annual_rate, int(tenure))

            loan_details_for_letter = {
                "approved_amount": approved_amount,
                "interest_rate": f"{annual_rate}%",
                "tenure": tenure,
            }
            letter_result = master_agent.sanction_generator.generate_letter(customer_details, loan_details_for_letter)

            # Generate AI-powered approval message with insights
            if gemini_agent.is_configured():
                credit_score = underwriting_result.get("credit_score", customer_details.get("credit_score", 750))
                ai_message = gemini_agent.generate_contextual_message(
                    context_type="explaining_approval",
                    customer=customer_details,
                    loan_details={"approved_amount": approved_amount, "tenure": tenure, "emi": emi, "rate": annual_rate},
                    extra_context=f"Approved! Credit score: {credit_score}. Explain why approved, what the EMI means for their ₹{customer_details.get('salary', 0):,} salary, and next steps. Be celebratory but professional."
                )
                response_message += (
                    f"\n\n{ai_message}\n\n"
                    f"📋 Your Loan Summary:\n"
                    f"💰 Amount: ₹{int(approved_amount):,}\n"
                    f"📅 Tenure: {tenure} months\n"
                    f"📊 Interest Rate: {annual_rate}% per annum\n"
                    f"💳 Monthly EMI: ₹{emi:,}\n\n"
                    f"✅ Your sanction letter is ready for download."
                )
            else:
                response_message += (
                    f"\n\n🎉 Congratulations, {customer_details.get('name', 'there')}! "
                    f"Your loan of ₹{int(approved_amount):,} has been approved!\n\n"
                    f"📋 Loan Details:\n"
                    f"• Amount: ₹{int(approved_amount):,}\n"
                    f"• Tenure: {tenure} months\n"
                    f"• Interest Rate: {annual_rate}% per annum\n"
                    f"• Monthly EMI: ₹{emi:,}\n\n"
                    f"Your sanction letter is ready for download."
                )
            session["state"] = "CONVERSATION_END"

            if letter_result.get("status") == "success":
                payload = letter_result.get("payload") or {
                    "name": customer_details.get("name"),
                    "amount": approved_amount,
                    "rate": annual_rate,
                    "emi": emi,
                }
                payload.setdefault("name", customer_details.get("name"))
                payload.setdefault("amount", approved_amount)
                payload.setdefault("rate", annual_rate)
                payload.setdefault("emi", emi)

                meta["action"] = "DOWNLOAD_PDF"
                meta["payload"] = payload

                try:
                    customer_db.record_application(
                        phone=customer_details["phone"],
                        amount=int(approved_amount),
                        status="APPROVED",
                        offer_selected={
                            "tenure": int(tenure),
                            "emi": int(payload.get("emi") or 0),
                            "rate": float(payload.get("rate") or 10.99),
                        },
                        score=int(underwriting_result.get("credit_score") or 750),
                    )
                except Exception:
                    pass
            else:
                response_message += "\n\nThere was an issue generating your sanction letter. Please contact support."

        elif underwriting_result.get("status") == "pending_salary_slip":
            session["state"] = "AWAITING_SALARY_UPLOAD"
            session["pending"] = {
                **pending,
                "awaiting_docs_for_amount": final_amount,
            }
            response_message = (
                (underwriting_result.get("reason") or "To proceed, please upload your latest salary slip.")
                + "\n\nType 'uploaded' once done (demo)."
            )
        else:
            response_message = underwriting_result.get("reason") or "Your request could not be approved."
            session["state"] = "CONVERSATION_END"

        return {"message": response_message, "meta": meta}

    if session["state"] == "AWAITING_SALARY_UPLOAD":
        if "upload" not in user_message.lower():
            return {"message": "No worries — type 'uploaded' after you upload your salary slip (demo).", "meta": {}}

        tenure = int(loan_details.get("tenure") or 0)
        approved_amount = int(pending.get("awaiting_docs_for_amount") or loan_details.get("final_amount") or 0)
        annual_rate = 10.99
        emi = _compute_emi(int(approved_amount), annual_rate, int(tenure))

        response_message = "Thanks! I’ve verified your document (demo). Your loan has been approved."

        meta["action"] = "DOWNLOAD_PDF"
        meta["payload"] = {
            "name": customer_details.get("name"),
            "amount": approved_amount,
            "rate": annual_rate,
            "emi": emi,
        }

        try:
            customer_db.record_application(
                phone=customer_details["phone"],
                amount=int(approved_amount),
                status="APPROVED_AFTER_DOCS",
                offer_selected={
                    "tenure": int(tenure),
                    "emi": int(emi),
                    "rate": float(annual_rate),
                },
                score=int(customer_details.get("credit_score") or 750),
            )
        except Exception:
            pass

        session["state"] = "CONVERSATION_END"
        return {"message": response_message, "meta": meta}

    if session["state"] == "CONVERSATION_END":
        if not response_message:
            response_message = "This conversation has concluded. Please start a new chat to begin again."
        meta["ended"] = True

    return {"message": response_message, "meta": meta}


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """JSON API used by the Next.js application."""
    body = request.json or {}
    user_message = body.get("message", "")
    session_id = body.get("sessionId")

    session = _get_or_create_session(session_id)
    result = _process_message(session, user_message)

    return jsonify(
        {
            "sessionId": session["id"],
            "message": result.get("message"),
            "meta": result.get("meta", {}),
        }
    )


@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT") or "5000")
    app.run(port=port, debug=True)
