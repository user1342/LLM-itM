from typing import Dict, Any
from .base import BaseModule


class ContentModerationModule(BaseModule):
    """Module for content moderation"""
    
    def get_description(self) -> str:
        return "Filters inappropriate content"
    
    def _process_request(self, request_data: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
        # Simple content filtering example
        banned_words = ["hack", "exploit", "malware"]
        
        messages = request_data.get("messages", [])
        for message in messages:
            content = message.get("content", "").lower()
            for word in banned_words:
                if word in content:
                    self.logger.warning(f"Blocked request containing banned word: {word}")
                    message["content"] = message["content"].replace(word, "[FILTERED]")
        
        return request_data
    
    def _process_response(self, response_data: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
        # Filter response content if needed
        choices = response_data.get("choices", [])
        for choice in choices:
            if "message" in choice and "content" in choice["message"]:
                content = choice["message"]["content"]
                # Apply filtering logic here
                choice["message"]["content"] = content
        
        return response_data
