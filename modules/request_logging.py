from typing import Dict, Any
from .base import BaseModule


class RequestLoggingModule(BaseModule):
    """Module for logging requests"""
    
    def get_description(self) -> str:
        return "Logs incoming requests for debugging"
    
    def _process_request(self, request_data: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info(f"Incoming request: {request_data.get('model', 'unknown')} - {len(request_data.get('messages', []))} messages")
        return request_data
    
    def _process_response(self, response_data: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info(f"Outgoing response: {response_data.get('model', 'unknown')} - {response_data.get('usage', {})}")
        return response_data
