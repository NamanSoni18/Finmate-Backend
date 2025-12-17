# mock_apis/server.py
from flask import Flask, jsonify, request
import sys
import os

# Add the project root to the Python path to import our database utility
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.database import customer_db

# Create a Flask application instance
app = Flask(__name__)

# --- API Endpoint 1: Credit Bureau ---
@app.route('/api/credit-bureau/score', methods=['GET'])
def get_credit_score():
    """
    Mock Credit Bureau API.
    In a real product, this would make an authenticated call to an external service like CIBIL.
    It would require API keys, customer consent, and robust error handling.
    """
    # Get the phone number from the query parameters (e.g., /api/credit-bureau/score?phone=9876543210)
    phone_number = request.args.get('phone')
    
    if not phone_number:
        return jsonify({"error": "Phone number is required"}), 400

    customer = customer_db.get_customer_by_phone(phone_number)
    
    if customer:
        # Return the credit score from our mock database
        return jsonify({
            "phone": phone_number,
            "credit_score": customer['credit_score'],
            "bureau": "MockCIBIL"
        })
    else:
        # Return a 404 Not Found if the customer doesn't exist
        return jsonify({"error": "Customer not found"}), 404

# --- API Endpoint 2: Offer Mart ---
@app.route('/api/offer-mart/pre-approved', methods=['GET'])
def get_pre_approved_offer():
    """
    Mock Offer Mart API.
    This service would typically contain complex business logic to generate personalized offers.
    """
    phone_number = request.args.get('phone')
    
    if not phone_number:
        return jsonify({"error": "Phone number is required"}), 400

    customer = customer_db.get_customer_by_phone(phone_number)
    
    if customer:
        # Return the pre-approved limit from our mock database
        return jsonify({
            "phone": phone_number,
            "customer_name": customer['name'],
            "pre_approved_limit": customer['pre_approved_limit'],
            "interest_rate": "10.99%", # Static for the prototype
            "status": "Offer Available"
        })
    else:
        return jsonify({"error": "Customer not found"}), 404

# --- Main entry point to run the server ---
if __name__ == '__main__':
    # In a real product, this would be run by a production-grade server like Gunicorn or uWSGI
    # and would be hosted on a proper domain, not localhost.
    port = int(os.environ.get("MOCK_API_PORT") or "5001")
    print(f"Starting Mock API Server on http://127.0.0.1:{port}")
    app.run(port=port, debug=True)