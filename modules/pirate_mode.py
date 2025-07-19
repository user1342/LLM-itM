from typing import Dict, Any
from .base import BaseModule


class PirateModeModule(BaseModule):
    """Module that makes the AI respond like a pirate"""
    
    def get_description(self) -> str:
        return "Makes the AI respond like a pirate (prepends instruction to user messages)"
    
    def _process_request(self, request_data: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
        if 'messages' in request_data:
            messages = request_data['messages']
            if messages and isinstance(messages, list):
                # Find the last user message and prepend pirate instruction
                for i in range(len(messages) - 1, -1, -1):
                    if messages[i].get('role') == 'user':
                        original_content = messages[i].get('content', '')
                        messages[i]['content'] = f"Respond like a pirate. {original_content}"
                        break
        
        return request_data
    
    def _process_response(self, response_data: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
        if 'choices' in response_data:
            for choice in response_data['choices']:
                if 'message' in choice and 'content' in choice['message']:
                    original_content = choice['message']['content']
                    choice['message']['content'] = f"{original_content}\n\n[Told to respond like a pirate]"
        
        return response_data
