# agents/document_verification_agent.py

from __future__ import annotations

import math
from typing import Any, Dict, Optional

from utils.database import customer_db


def _compute_emi(principal: int, annual_rate_percent: float, tenure_months: int) -> int:
    if principal <= 0 or tenure_months <= 0:
        return 0

    monthly_rate = (annual_rate_percent / 100.0) / 12.0
    if monthly_rate <= 0:
        return int(math.ceil(principal / tenure_months))

    factor = (1 + monthly_rate) ** tenure_months
    emi = principal * monthly_rate * factor / (factor - 1)
    return int(round(emi))


class DocumentVerificationAgent:
    """Simulates document verification (salary slip) for the prototype."""

    def verify_salary_slip(
        self,
        phone_number: str,
        *,
        requested_amount: int,
        tenure_months: int = 60,
        annual_rate_percent: float = 10.99,
        max_emi_percent: int = 50,
    ) -> Dict[str, Any]:
        customer = customer_db.get_customer_by_phone(phone_number)
        if not customer:
            return {"status": "error", "message": "Customer not found."}

        salary = customer.get("salary")
        if salary is None:
            # Prototype fallback: if salary isn't available, approve verification.
            return {
                "status": "verified",
                "message": "Document verified (salary not available; prototype auto-pass).",
            }

        try:
            monthly_salary = float(salary)
        except Exception:
            monthly_salary = 0.0

        emi = _compute_emi(int(requested_amount), float(annual_rate_percent), int(tenure_months))
        limit = (max_emi_percent / 100.0) * monthly_salary

        if monthly_salary <= 0:
            return {
                "status": "error",
                "message": "Invalid salary data; cannot verify document.",
            }

        if emi <= limit:
            return {
                "status": "verified",
                "message": "Document verified. EMI is within allowed salary threshold.",
                "emi": emi,
                "emi_limit": int(limit),
            }

        return {
            "status": "rejected",
            "message": "Document verification failed: EMI exceeds allowed salary threshold.",
            "emi": emi,
            "emi_limit": int(limit),
        }
