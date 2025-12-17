# test_apis.py
import os
import requests


def _try_load_env() -> None:
    """Best-effort load of .env/.env.local for local testing."""
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return

    here = os.path.abspath(__file__)
    repo_root = os.path.abspath(os.path.join(os.path.dirname(here), "..", ".."))
    service_root = os.path.abspath(os.path.dirname(here))

    for env_path in (
        os.path.join(repo_root, ".env.local"),
        os.path.join(repo_root, ".env"),
        os.path.join(service_root, ".env"),
        os.path.join(service_root, ".env.local"),
    ):
        if os.path.exists(env_path):
            load_dotenv(env_path, override=False)


_try_load_env()

# The base URL for our mock API server
API_BASE_URL = os.environ.get("MOCK_API_BASE_URL") or "http://127.0.0.1:5001"

def test_api_endpoints():
    print("--- Testing Mock API Endpoints ---")
    
    # --- Test Case 1: Valid Customer ---
    print("\n[TEST 1] Fetching data for a valid customer (Rajesh Kumar)...")
    test_phone = "9876543210"
    
    try:
        # Test Credit Bureau API
        credit_url = f"{API_BASE_URL}/api/credit-bureau/score?phone={test_phone}"
        credit_response = requests.get(credit_url)
        print(f"✅ Credit Bureau API Status: {credit_response.status_code}")
        print(f"   Response: {credit_response.json()}")
        
        # Test Offer Mart API
        offer_url = f"{API_BASE_URL}/api/offer-mart/pre-approved?phone={test_phone}"
        offer_response = requests.get(offer_url)
        print(f"✅ Offer Mart API Status: {offer_response.status_code}")
        print(f"   Response: {offer_response.json()}")
        
    except requests.exceptions.ConnectionError:
        print("❌ FAILED: Connection Error. Is the API server running?")
        print("   Please run 'python mock_apis/server.py' in another terminal.")
        return

    # --- Test Case 2: Invalid Customer ---
    print("\n[TEST 2] Fetching data for a non-existent customer...")
    invalid_phone = "1234567890"
    
    credit_url = f"{API_BASE_URL}/api/credit-bureau/score?phone={invalid_phone}"
    credit_response = requests.get(credit_url)
    print(f"✅ Credit Bureau API Status: {credit_response.status_code}")
    print(f"   Response: {credit_response.json()}")

    print("\n--- API Testing Complete ---")


if __name__ == "__main__":
    test_api_endpoints()