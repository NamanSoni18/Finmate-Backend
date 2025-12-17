# test_sentiment_analysis.py

import os
import sys

# Allow running this test directly (e.g. `python agents/test_sentiment_analysis.py`)
# by ensuring the loan_chatbot root is on sys.path.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agents.sentiment_analysis_agent import SentimentAnalysisAgent

def test_sentiment_analysis():
    """Test the sentiment analysis agent with various examples."""
    agent = SentimentAnalysisAgent()
    
    test_messages = [
        "I'm really happy with your service, thank you!",
        "This is taking too long, I'm getting frustrated",
        "I don't understand what you mean by pre-approved limit",
        "I need this urgently, can you help me right away?",
        "I'm confused about the interest rates",
        "Yes, I'd like to proceed with the loan",
        "No, that's not what I want",
        "Can you please explain this to me?",
        "This is terrible service, I'm very angry",
        "I'm worried about the repayment terms"
    ]
    
    print("=== Sentiment Analysis Test ===")
    for message in test_messages:
        result = agent.analyze_sentiment(message)
        response = agent.get_response_suggestion(result)
        should_escalate = agent.should_escalate(result)
        
        print(f"\nMessage: '{message}'")
        print(f"Sentiment: {result['sentiment']} (confidence: {result['confidence']:.2f})")
        print(f"Dominant state: {result['dominant_state']}")
        print(f"Detected states: {result['detected_states']}")
        print(f"Suggested response: '{response}'")
        print(f"Should escalate: {should_escalate}")

if __name__ == '__main__':
    test_sentiment_analysis()