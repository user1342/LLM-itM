from typing import Dict, Any
from .base import BaseModule


class ResponseFilteringModule(BaseModule):
    """Module for response filtering and modification"""
    
    def get_description(self) -> str:
        return "Filters and modifies responses"
    
    def _process_request(self, request_data: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
        # Add system prompt prefix if configured
        system_prefix = settings.get("system_prompt_prefix", "")
        if system_prefix:
            messages = request_data.get("messages", [])
            for message in messages:
                if message.get("role") == "system":
                    message["content"] = f"{system_prefix}\n{message['content']}"
        
        # Override temperature if set
        temp_override = settings.get("temperature_override", "")
        if temp_override:
            try:
                request_data["temperature"] = float(temp_override)
            except ValueError:
                pass
        
        # Set max tokens limit
        max_tokens = settings.get("max_tokens_limit", "")
        if max_tokens:
            try:
                request_data["max_tokens"] = int(max_tokens)
            except ValueError:
                pass
        
        return request_data
    
    def _process_response(self, response_data: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
        # Apply response format if needed
        response_format = settings.get("response_format", "json")
        if response_format != "json":
            # Could modify response format here
            pass
        
        return response_data
