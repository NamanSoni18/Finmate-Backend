# verify_setup.py
from utils.database import customer_db

def main():
    print("--- Tata Capital Chatbot: Setup Verification ---")

    # Print backend information when available
    try:
        if hasattr(customer_db, "debug_backend"):
            info = customer_db.debug_backend()
            print(f"✅ Using backend: {info}")
        else:
            print("✅ Using backend: json")
    except Exception:
        pass
    
    # Test 1: Check if we can retrieve a specific customer
    test_phone = "9876543210" # Rajesh Kumar's phone
    customer = customer_db.get_customer_by_phone(test_phone)
    
    if customer:
        print(f"✅ SUCCESS: Found customer '{customer.get('name')}' with phone {test_phone}.")
        if 'credit_score' in customer:
            print(f"   - Credit Score: {customer['credit_score']}")
        if 'pre_approved_limit' in customer:
            print(f"   - Pre-Approved Limit: ₹{customer['pre_approved_limit']:,}")
    else:
        print(f"❌ FAILED: Could not find customer with phone {test_phone}.")

        # If Mongo is configured, show a hint so you can test with a real phone.
        try:
            if hasattr(customer_db, "users"):
                sample = customer_db.users.find_one({})
                if sample:
                    print("ℹ️ Hint: Found a user in MongoDB. Try testing with their phone:")
                    print(f"   - name: {sample.get('name')}")
                    print(f"   - phone: {sample.get('phone')}")
        except Exception:
            pass

    print("\n--- Verification Complete ---")

if __name__ == "__main__":
    main()