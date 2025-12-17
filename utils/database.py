# utils/database.py
import json
import os
import datetime
from typing import Any, Dict, Optional


def _try_load_env_from_repo_root() -> None:
    """Best-effort load of finmate/.env.local so Python can reuse Next.js env vars."""
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return

    # This file lives at: finmate/loan_chatbot/loan_chatbot/utils/database.py
    # Next.js env file typically lives at: finmate/.env.local (or .env)
    here = os.path.abspath(__file__)
    repo_root = os.path.abspath(os.path.join(os.path.dirname(here), "..", "..", ".."))

    python_service_root = os.path.dirname(os.path.dirname(here))
    frontend_root = os.path.join(repo_root, "Frontend")

    candidates = [
        # Prefer python-service envs (for separate deployments).
        os.path.join(python_service_root, ".env"),
        os.path.join(python_service_root, ".env.local"),
        # Repo-root envs (common convention)
        os.path.join(repo_root, ".env.local"),
        os.path.join(repo_root, ".env"),
        # Next.js envs live under Frontend/ in this repo
        os.path.join(frontend_root, ".env.local"),
        os.path.join(frontend_root, ".env"),
    ]
    for env_path in candidates:
        if os.path.exists(env_path):
            load_dotenv(env_path, override=False)


class JsonCustomerDatabase:
    """Legacy JSON database used when MongoDB is not configured."""

    def __init__(self):
        self.customers: Dict[str, Dict[str, Any]] = {}
        self.load_customers()

    def load_customers(self) -> None:
        project_root = os.path.dirname(os.path.dirname(__file__))
        file_path = os.path.join(project_root, "data", "customers.json")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                customers_data = json.load(f)
                for customer in customers_data:
                    self.customers[customer["phone"]] = customer
        except FileNotFoundError:
            # Keep the prototype usable even when MongoDB is unavailable and
            # the JSON fixture file isn't present (common in fresh clones).
            self.customers = {
                "9876543210": {
                    "customer_id": "demo_9876543210",
                    "name": "Rajesh Kumar",
                    "phone": "9876543210",
                    "email": "rajesh.kumar@email.com",
                    "address": "Mumbai",
                    "pre_approved_limit": 500000,
                    "credit_score": 750,
                },
                "9876543211": {
                    "customer_id": "demo_9876543211",
                    "name": "Priya Sharma",
                    "phone": "9876543211",
                    "email": "priya.sharma@email.com",
                    "address": "Delhi",
                    "pre_approved_limit": 750000,
                    "credit_score": 780,
                },
            }
            print(
                f"[DB] ⚠️ {file_path} not found; using built-in demo customers (JSON mode)."
            )
        except json.JSONDecodeError:
            print(f"Error: The file {file_path} contains invalid JSON.")

    def get_customer_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        return self.customers.get(phone)

    def record_application(
        self,
        *,
        phone: str,
        amount: int,
        status: str,
        offer_selected: Optional[Dict[str, Any]] = None,
        score: int = 750,
    ) -> None:
        # No-op for JSON mode.
        return


class MongoCustomerDatabase:
    """MongoDB database adapter compatible with your Next.js Mongoose schemas.

    Collections:
    - users (from models/User.ts)
    - applications (from models/Application.ts)
    """

    def __init__(self, mongo_uri: str):
        from pymongo import MongoClient  # type: ignore

        self.mongo_uri = mongo_uri
        # Avoid hanging when MongoDB is unreachable (common in hackathon/demo setups),
        # but don't be so aggressive that normal DNS/TLS handshakes fail.
        server_selection_timeout_ms = int(
            os.environ.get("MONGO_SERVER_SELECTION_TIMEOUT_MS") or "10000"
        )
        connect_timeout_ms = int(os.environ.get("MONGO_CONNECT_TIMEOUT_MS") or "10000")
        socket_timeout_ms = int(os.environ.get("MONGO_SOCKET_TIMEOUT_MS") or "10000")

        self.client = MongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=server_selection_timeout_ms,
            connectTimeoutMS=connect_timeout_ms,
            socketTimeoutMS=socket_timeout_ms,
        )

        # Force a quick connectivity check so we can fall back if needed.
        self.client.admin.command("ping")

        # Use the default database from the URI when present.
        # If none is specified (common in Next.js demos), default to the same behavior
        # Mongoose uses: "test".
        try:
            self.db = self.client.get_default_database()
            self.db_name = self.db.name
        except Exception:
            db_name = (
                os.environ.get("MONGODB_DB_NAME")
                or os.environ.get("MONGO_DB_NAME")
                or "test"
            )
            self.db = self.client[db_name]
            self.db_name = db_name

        self.users = self.db["users"]
        self.applications = self.db["applications"]

    def debug_backend(self) -> Dict[str, Any]:
        return {"backend": "mongo", "db": self.db_name}

    def _normalize_user(self, user_doc: Dict[str, Any]) -> Dict[str, Any]:
        credit_history = user_doc.get("creditHistory") or []
        credit_score = 750
        if isinstance(credit_history, list) and len(credit_history) > 0:
            last = credit_history[-1]
            if isinstance(last, dict) and isinstance(last.get("score"), (int, float)):
                credit_score = int(last["score"])

        city = user_doc.get("city") or ""
        return {
            "customer_id": str(user_doc.get("_id")),
            "name": user_doc.get("name"),
            "phone": user_doc.get("phone"),
            "email": user_doc.get("email"),
            # Python prototype expects an address; Next.js stores city.
            "address": city,
            # Prototype expects snake_case.
            "pre_approved_limit": int(user_doc.get("preApprovedLimit") or 0),
            "credit_score": credit_score,
            # Extra fields that may be useful for future logic.
            "salary": user_doc.get("salary"),
            "kyc_status": user_doc.get("kycStatus"),
            "pan": user_doc.get("pan"),
            "aadhaar": user_doc.get("aadhaar"),
        }

    def get_customer_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        user = self.users.find_one({"phone": phone})
        if not user:
            return None
        return self._normalize_user(user)

    def record_application(
        self,
        *,
        phone: str,
        amount: int,
        status: str,
        offer_selected: Optional[Dict[str, Any]] = None,
        score: int = 750,
    ) -> None:
        user = self.users.find_one({"phone": phone})
        if not user:
            return

        user_id = user.get("_id")
        now = datetime.datetime.utcnow()
        app_doc: Dict[str, Any] = {
            "userId": user_id,
            "amount": int(amount),
            "status": status,
            "createdAt": now,
        }
        if offer_selected:
            app_doc["offerSelected"] = offer_selected
        self.applications.insert_one(app_doc)

        update: Dict[str, Any] = {
            "$push": {
                "creditHistory": {
                    "date": now,
                    "amount": int(amount),
                    "status": status,
                    "score": int(score),
                }
            }
        }
        if status.upper().startswith("APPROVED"):
            update["$set"] = {"currentLoanAmount": int(amount)}
        self.users.update_one({"_id": user_id}, update)


_try_load_env_from_repo_root()


def _build_customer_db():
    mongo_uri = os.environ.get("MONGODB_URI")
    if mongo_uri:
        try:
            return MongoCustomerDatabase(mongo_uri)
        except Exception as e:
            print(f"[DB] ⚠️ Failed to connect to MongoDB, falling back to JSON: {e}")
            return JsonCustomerDatabase()
    return JsonCustomerDatabase()


# Global instance used by agents
customer_db = _build_customer_db()