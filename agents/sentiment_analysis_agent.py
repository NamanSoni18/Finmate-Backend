# agents/sentiment_analysis_agent.py

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

class SentimentAnalysisAgent:
    """
    Analyzes user messages for sentiment and emotional intent.
    This prototype uses keyword-based sentiment analysis.
    In production, you might want to use an NLP library or API.
    """
    
    def __init__(self):
        # Define sentiment keywords and patterns
        self.positive_keywords = [
            "happy", "satisfied", "good", "great", "excellent", "thank", "thanks", 
            "perfect", "wonderful", "amazing", "love", "like", "appreciate", 
            "excited", "pleased", "delighted", "yes", "sure", "absolutely"
        ]
        
        self.negative_keywords = [
            "unhappy", "disappointed", "bad", "terrible", "awful", "hate", 
            "dislike", "frustrated", "angry", "upset", "annoyed", "confused", 
            "worried", "concerned", "no", "not", "never", "impossible", "wrong"
        ]
        
        self.urgency_keywords = [
            "urgent", "asap", "immediately", "quickly", "fast", "soon", 
            "hurry", "emergency", "need", "required", "waiting"
        ]
        
        self.confusion_keywords = [
            "confused", "don't understand", "unclear", "what do you mean", 
            "explain", "how", "why", "help", "not sure", "clarify"
        ]
        
        # Define emotional states
        self.emotional_states = {
            "positive": {
                "keywords": self.positive_keywords,
                "responses": [
                    "I'm glad I could help you with that!",
                    "That's wonderful to hear!",
                    "Thank you for your positive feedback!",
                    "I'm happy to assist you further."
                ]
            },
            "negative": {
                "keywords": self.negative_keywords,
                "responses": [
                    "I understand your concern. Let me help resolve this.",
                    "I apologize for any inconvenience. How can I make this better?",
                    "I'm sorry to hear that. Let's see what I can do.",
                    "Your feedback is important. Let me address your concerns."
                ]
            },
            "urgent": {
                "keywords": self.urgency_keywords,
                "responses": [
                    "I understand this is urgent. Let me expedite your request.",
                    "I'll prioritize your request right away.",
                    "I understand time is important. Let me help you quickly.",
                    "I'll make sure this gets immediate attention."
                ]
            },
            "confused": {
                "keywords": self.confusion_keywords,
                "responses": [
                    "I'd be happy to clarify. Let me explain in more detail.",
                    "I understand this might be confusing. Let me break it down for you.",
                    "Let me provide more information to help you understand.",
                    "I'm here to help. Let me explain this step by step."
                ]
            }
        }
    
    def analyze_sentiment(self, message: str) -> Dict[str, Any]:
        """
        Analyzes the sentiment of a user message.
        
        Args:
            message (str): The user's message
            
        Returns:
            dict: A dictionary containing sentiment analysis results
        """
        if not message:
            return {"sentiment": "neutral", "confidence": 0.0, "emotional_states": []}
        
        message_lower = message.lower()
        
        # Count occurrences of keywords for each emotional state
        state_scores = {}
        for state, config in self.emotional_states.items():
            score = 0
            for keyword in config["keywords"]:
                # Count occurrences of the keyword
                pattern = r'\b' + re.escape(keyword) + r'\b'
                matches = re.findall(pattern, message_lower)
                score += len(matches)
            state_scores[state] = score
        
        # Determine the dominant emotional state
        if sum(state_scores.values()) == 0:
            dominant_state = "neutral"
            confidence = 0.0
        else:
            dominant_state = max(state_scores.items(), key=lambda x: x[1])[0]
            confidence = min(1.0, state_scores[dominant_state] / 5.0)  # Normalize to 0-1
        
        # Get all detected emotional states (with score > 0)
        detected_states = [state for state, score in state_scores.items() if score > 0]
        
        # Determine overall sentiment (positive, negative, or neutral)
        if dominant_state in ["positive", "negative"]:
            sentiment = dominant_state
        else:
            sentiment = "neutral"
        
        return {
            "sentiment": sentiment,
            "confidence": confidence,
            "dominant_state": dominant_state,
            "detected_states": detected_states,
            "state_scores": state_scores
        }
    
    def get_response_suggestion(self, sentiment_result: Dict[str, Any]) -> str:
        """
        Gets a response suggestion based on sentiment analysis.
        
        Args:
            sentiment_result (dict): The result from analyze_sentiment
            
        Returns:
            str: A suggested response
        """
        dominant_state = sentiment_result.get("dominant_state", "neutral")
        
        if dominant_state in self.emotional_states:
            import random
            responses = self.emotional_states[dominant_state]["responses"]
            return random.choice(responses)
        
        return ""
    
    def should_escalate(self, sentiment_result: Dict[str, Any]) -> bool:
        """
        Determines if the conversation should be escalated based on sentiment.
        
        Args:
            sentiment_result (dict): The result from analyze_sentiment
            
        Returns:
            bool: True if escalation is recommended
        """
        # Escalate if negative sentiment is high or if multiple negative indicators
        if sentiment_result.get("sentiment") == "negative" and sentiment_result.get("confidence", 0) > 0.6:
            return True
        
        # Escalate if both negative and urgent states are detected
        detected_states = sentiment_result.get("detected_states", [])
        if "negative" in detected_states and "urgent" in detected_states:
            return True
        
        return False