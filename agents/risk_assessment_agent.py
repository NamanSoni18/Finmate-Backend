# agents/risk_assessment_agent.py

from __future__ import annotations

from typing import Any, Dict

from agents.credit_bureau_agent import CreditBureauAgent
from utils.database import customer_db


class RiskAssessmentAgent:
    """Calculates a risk score and returns an underwriting decision."""

    def __init__(self):
        self.credit_bureau_agent = CreditBureauAgent()

    def assess(self, phone_number: str, requested_amount: int) -> Dict[str, Any]:
        if not phone_number:
            return {"status": "error", "message": "Phone number cannot be empty."}
        if not isinstance(requested_amount, int) or requested_amount <= 0:
            return {"status": "error", "message": "Requested amount must be a positive integer."}

        credit = self.credit_bureau_agent.get_credit_report(phone_number)
        if credit.get("status") != "success":
            return {"status": "error", "message": credit.get("message") or "Credit report unavailable."}

        credit_score = int(credit.get("credit_score") or 0)

        customer = customer_db.get_customer_by_phone(phone_number)
        if not customer:
            return {"status": "error", "message": "Customer not found."}

        pre_approved_limit = int(customer.get("pre_approved_limit") or 0)

        # Simple prototype risk scoring: higher score = safer.
        #  - credit contributes up to 70 points
        #  - utilization contributes up to 30 points
        credit_component = max(0, min(70, int((credit_score - 600) * 0.35)))
        utilization = 1.0
        if pre_approved_limit > 0:
            utilization = requested_amount / float(pre_approved_limit)
        utilization_component = max(0, min(30, int((2.0 - utilization) * 15)))
        risk_score = max(0, min(100, credit_component + utilization_component))

        # Decision rules (kept consistent with existing underwriting_agent behavior)
        if credit_score < 700:
            return {
                "status": "rejected",
                "reason": (
                    f"Unfortunately, your application could not be approved as your credit score ({credit_score}) "
                    "is below our minimum requirement."
                ),
                "risk_score": risk_score,
                "credit_score": credit_score,
                "pre_approved_limit": pre_approved_limit,
            }

        if requested_amount <= pre_approved_limit:
            return {
                "status": "approved_instant",
                "reason": "Congratulations! Your loan has been instantly approved based on your pre-approved offer.",
                "approved_amount": requested_amount,
                "risk_score": risk_score,
                "credit_score": credit_score,
                "pre_approved_limit": pre_approved_limit,
            }

        if pre_approved_limit > 0 and requested_amount <= 2 * pre_approved_limit:
            return {
                "status": "pending_salary_slip",
                "reason": "Your request is being processed. To proceed, please upload your latest salary slip for verification.",
                "max_emi_percent": 50,
                "risk_score": risk_score,
                "credit_score": credit_score,
                "pre_approved_limit": pre_approved_limit,
            }

        return {
            "status": "rejected",
            "reason": (
                "Unfortunately, we cannot approve the requested amount. "
                f"The maximum amount we can offer is ₹{2 * pre_approved_limit:,}."
            ),
            "risk_score": risk_score,
            "credit_score": credit_score,
            "pre_approved_limit": pre_approved_limit,
        }
