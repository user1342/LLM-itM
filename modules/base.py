from abc import ABC, abstractmethod
from typing import Dict, Any
import logging


class BaseModule(ABC):
    """Base class for all processing modules"""
    
    def __init__(self):
        # Module name is automatically derived from class name
        self.name = self.__class__.__name__.lower().replace('module', '')
        self.description = self.get_description()
        self.logger = logging.getLogger(f"module.{self.name}")
    
    @abstractmethod
    def get_description(self) -> str:
        """Return a description of what this module does"""
        pass
    
    def process_request(self, request_data: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming request data - override if needed"""
        if not self.is_enabled(settings):
            return request_data
        return self._process_request(request_data, settings)
    
    def process_response(self, response_data: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
        """Process outgoing response data - override if needed"""
        if not self.is_enabled(settings):
            return response_data
        return self._process_response(response_data, settings)
    
    def _process_request(self, request_data: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
        """Override this method in subclasses for request processing"""
        return request_data
    
    def _process_response(self, response_data: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
        """Override this method in subclasses for response processing"""
        return response_data
    
    def is_enabled(self, settings: Dict[str, Any]) -> bool:
        """Check if this module is enabled in settings"""
        setting_name = f"use_{self.name}"
        return settings.get(setting_name, True)  # Default to enabled
    
    def get_setting_name(self) -> str:
        """Get the setting name for this module"""
        return f"use_{self.name}"
