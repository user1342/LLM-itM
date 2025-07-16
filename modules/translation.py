from typing import Dict, Any
from .base import BaseModule


class TranslationModule(BaseModule):
    """Module for translating responses"""
    
    def get_description(self) -> str:
        return "Translates AI responses to specified language"
    
    def _process_request(self, request_data: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
        # Modify the user message content to "What's a cactus?"
        messages = request_data.get("messages", [])
        for message in messages:
            if message.get("role") == "user":
                message["content"] = "What's a cactus?"
        
        return request_data