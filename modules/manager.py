import os
import importlib
import pkgutil
from typing import List, Dict, Any
from .base import BaseModule


class ModuleManager:
    """Automatically discovers and manages all processing modules"""
    
    def __init__(self):
        self.modules: List[BaseModule] = []
        self._discover_modules()
    
    def _discover_modules(self):
        """Automatically discover all modules in the modules directory"""
        modules_path = os.path.dirname(__file__)
        
        # Get all Python files in the modules directory (except __init__.py and base.py)
        for _, module_name, _ in pkgutil.iter_modules([modules_path]):
            if module_name in ['__init__', 'base', 'manager']:
                continue
            
            try:
                # Import the module
                module = importlib.import_module(f'.{module_name}', package='modules')
                
                # Find all classes that inherit from BaseModule
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and 
                        issubclass(attr, BaseModule) and 
                        attr != BaseModule):
                        # Instantiate the module
                        instance = attr()
                        self.modules.append(instance)
                        print(f"Loaded module: {instance.name} - {instance.description}")
            
            except Exception as e:
                print(f"Failed to load module {module_name}: {e}")
    
    def get_module_settings(self) -> Dict[str, Any]:
        """Get default settings for all discovered modules"""
        settings = {}
        for module in self.modules:
            settings[module.get_setting_name()] = True  # Default to enabled
        return settings
    
    def process_request(self, request_data: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
        """Process request through all enabled modules"""
        for module in self.modules:
            if module.is_enabled(settings):
                request_data = module.process_request(request_data, settings)
        return request_data
    
    def process_response(self, response_data: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
        """Process response through all enabled modules"""
        for module in self.modules:
            if module.is_enabled(settings):
                response_data = module.process_response(response_data, settings)
        return response_data
    
    def get_module_info(self) -> List[Dict[str, str]]:
        """Get information about all available modules"""
        return [
            {
                "name": module.name,
                "description": module.description,
                "setting_name": module.get_setting_name(),
                "class_name": module.__class__.__name__
            }
            for module in self.modules
        ]
