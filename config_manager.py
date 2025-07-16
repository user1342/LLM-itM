import json
import os
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum


class SettingType(Enum):
    TEXT = "text"
    BOOLEAN = "boolean"
    DROPDOWN = "dropdown"


@dataclass
class Setting:
    name: str
    type: SettingType
    default_value: Any
    description: str
    options: Optional[List[str]] = None  # For dropdown settings
    
    def to_dict(self):
        return {
            "name": self.name,
            "type": self.type.value,
            "default_value": self.default_value,
            "description": self.description,
            "options": self.options
        }


class ConfigManager:
    def __init__(self, config_file="config.json"):
        self.config_file = config_file
        
        # Auto-discover module settings
        from modules.manager import ModuleManager
        self.module_manager = ModuleManager()
        
        # Define core application settings
        self.available_settings = [
            Setting("max_tokens_limit", SettingType.TEXT, "2048", "Maximum tokens allowed (Ollama default)"),
            Setting("response_format", SettingType.DROPDOWN, "json", "Response format", ["json", "text", "markdown"]),
            Setting("temperature_override", SettingType.TEXT, "", "Override temperature (leave empty to use request value)"),
            Setting("system_prompt_prefix", SettingType.TEXT, "", "Prefix to add to system prompts"),
            Setting("enable_caching", SettingType.BOOLEAN, False, "Enable response caching"),
            Setting("log_level", SettingType.DROPDOWN, "INFO", "Logging level", ["DEBUG", "INFO", "WARNING", "ERROR"]),
            Setting("llm_provider", SettingType.DROPDOWN, "ollama", "LLM Provider", ["ollama", "openai", "custom"]),
            Setting("default_model", SettingType.TEXT, "llama3.1", "Default model to use")
        ]
        
        # Add module settings
        self._add_module_settings()
        
        self.settings = self.load_settings()
    
    def _add_module_settings(self):
        """Automatically add settings for discovered modules"""
        for module in self.module_manager.modules:
            setting = Setting(
                module.get_setting_name(),
                SettingType.BOOLEAN,
                True,  # Default to enabled
                f"Enable {module.description}"
            )
            self.available_settings.append(setting)
    
    def load_settings(self) -> Dict[str, Any]:
        """Load settings from config file or create default settings"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    saved_settings = json.load(f)
                
                # Merge with defaults for any missing settings
                settings = {}
                for setting in self.available_settings:
                    settings[setting.name] = saved_settings.get(setting.name, setting.default_value)
                
                return settings
            except Exception as e:
                print(f"Error loading config: {e}")
        
        # Return default settings
        return {setting.name: setting.default_value for setting in self.available_settings}
    
    def save_settings(self, settings: Dict[str, Any]) -> bool:
        """Save settings to config file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(settings, f, indent=2)
            self.settings = settings
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    def get_setting(self, name: str, default=None) -> Any:
        """Get a specific setting value"""
        return self.settings.get(name, default)
    
    def get_all_settings(self) -> Dict[str, Any]:
        """Get all current settings"""
        return self.settings.copy()
    
    def get_settings_schema(self) -> List[Dict]:
        """Get the schema for all available settings"""
        return [setting.to_dict() for setting in self.available_settings]
