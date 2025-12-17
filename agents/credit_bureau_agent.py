# agents/credit_bureau_agent.py

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional, Tuple

import requests

from utils.database import customer_db


class CreditBureauAgent:
    """Fetches credit report with caching.

    - Attempts the mock credit-bureau API when configured.
    - Falls back to the local DB adapter.
    """

    def __init__(self, *, cache_ttl_seconds: Optional[int] = None):
        self._cache_ttl = cache_ttl_seconds or int(
            os.environ.get("CREDIT_BUREAU_CACHE_TTL_SECONDS") or "300"
        )
        self._cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

    def get_credit_report(self, phone_number: str) -> Dict[str, Any]:
        phone_number = (phone_number or "").strip()
        if not phone_number:
            return {"status": "error", "message": "Phone number cannot be empty."}

        cached = self._get_cached(phone_number)
        if cached is not None:
            return {"status": "success", "source": "cache", **cached}

        api_base = os.environ.get("MOCK_API_BASE_URL")
        if api_base:
            try:
                res = requests.get(
                    f"{api_base}/api/credit-bureau/score",
                    params={"phone": phone_number},
                    timeout=3,
                )
                res.raise_for_status()
                data = res.json()
                credit_score = int(data.get("credit_score"))
                report = {
                    "phone": phone_number,
                    "credit_score": credit_score,
                    "bureau": data.get("bureau") or "MockCIBIL",
                }
                self._set_cache(phone_number, report)
                return {"status": "success", "source": "mock_api", **report}
            except Exception:
                # Fall through to DB.
                pass

        customer = customer_db.get_customer_by_phone(phone_number)
        if not customer:
            return {"status": "error", "message": "Customer not found."}

        report = {
            "phone": phone_number,
            "credit_score": int(customer.get("credit_score") or 0),
            "bureau": "local",
        }
        self._set_cache(phone_number, report)
        return {"status": "success", "source": "db", **report}

    def _get_cached(self, phone_number: str) -> Optional[Dict[str, Any]]:
        item = self._cache.get(phone_number)
        if not item:
            return None
        ts, report = item
        if time.time() - ts > self._cache_ttl:
            self._cache.pop(phone_number, None)
            return None
        return report

    def _set_cache(self, phone_number: str, report: Dict[str, Any]) -> None:
        self._cache[phone_number] = (time.time(), report)
