import os
import json
import logging
from typing import Dict, Any

import openai
from flask import Flask, request, jsonify, render_template_string, redirect, url_for
from dotenv import load_dotenv

from config_manager import ConfigManager

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Initialize managers
config_manager = ConfigManager()
module_manager = config_manager.module_manager  # Get module manager from config manager

# Configure logging
logging.basicConfig(
    level=getattr(logging, config_manager.get_setting('log_level', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# LLM API Configuration (defaults to Ollama)
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', 'ollama')
OPENAI_BASE_URL = os.environ.get('OPENAI_BASE_URL', 'http://localhost:11434/v1')

if OPENAI_API_KEY == 'your_openai_api_key_here':
    logger.warning("Using default Ollama configuration. Set OPENAI_API_KEY for OpenAI API.")
    OPENAI_API_KEY = 'ollama'

# Initialize OpenAI client (works with Ollama too)
openai_client = openai.OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL
) if OPENAI_API_KEY else None


@app.route('/')
def settings_page():
    """Main settings page"""
    settings_schema = config_manager.get_settings_schema()
    current_settings = config_manager.get_all_settings()
    module_info = module_manager.get_module_info()
    
    return render_template_string(SETTINGS_TEMPLATE, 
                                  settings_schema=settings_schema,
                                  current_settings=current_settings,
                                  module_info=module_info)


@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    """API endpoint for managing settings"""
    if request.method == 'GET':
        return jsonify({
            'settings': config_manager.get_all_settings(),
            'schema': config_manager.get_settings_schema(),
            'modules': module_manager.get_module_info()
        })
    
    elif request.method == 'POST':
        try:
            new_settings = request.json
            if config_manager.save_settings(new_settings):
                return jsonify({'success': True, 'message': 'Settings saved successfully'})
            else:
                return jsonify({'success': False, 'message': 'Failed to save settings'}), 500
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 400


@app.route('/v1/models', methods=['GET'])
def list_models():
    """OpenAI API: List available models"""
    try:
        if not openai_client:
            return jsonify({'error': 'OpenAI client not configured'}), 500
        
        models = openai_client.models.list()
        return jsonify(models.model_dump()), 200
    
    except Exception as e:
        logger.error(f"Error listing models: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    """OpenAI API: Chat completions endpoint"""
    try:
        if not openai_client:
            return jsonify({'error': 'OpenAI client not configured'}), 500
        
        # Get current settings
        settings = config_manager.get_all_settings()
        # Get request data
        request_data = request.json
        # Process request through modules, allowing modules to update settings
        for module in module_manager.modules:
            if module.is_enabled(settings):
                request_data = module.process_request(request_data, settings)
                # If module updated settings, reflect changes
                if hasattr(module, 'update_settings'):
                    updated = module.update_settings(settings)
                    if updated:
                        settings.update(updated)
        logger.info(f"Forwarding request to OpenAI: {request_data.get('model', 'unknown')}")
        # Forward to OpenAI API using the client
        if request_data.get('stream', False):
            # Handle streaming response
            stream = openai_client.chat.completions.create(**request_data)
            def generate():
                for chunk in stream:
                    yield f"data: {chunk.model_dump_json()}\n\n"
                yield "data: [DONE]\n\n"
            return app.response_class(
                generate(),
                mimetype='text/plain',
                headers={'Content-Type': 'text/event-stream'}
            )
        else:
            # Handle regular response
            response = openai_client.chat.completions.create(**request_data)
            response_data = response.model_dump()
            # Process response through modules, allowing modules to update settings
            for module in module_manager.modules:
                if module.is_enabled(settings):
                    response_data = module.process_response(response_data, settings)
                    if hasattr(module, 'update_settings'):
                        updated = module.update_settings(settings)
                        if updated:
                            settings.update(updated)
            return jsonify(response_data), 200
    
    except Exception as e:
        logger.error(f"Error in chat completions: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/v1/completions', methods=['POST'])
def completions():
    """OpenAI API: Text completions endpoint"""
    try:
        if not openai_client:
            return jsonify({'error': 'OpenAI client not configured'}), 500
        
        # Get current settings
        settings = config_manager.get_all_settings()
        # Get request data
        request_data = request.json
        # Process request through modules, allowing modules to update settings
        for module in module_manager.modules:
            if module.is_enabled(settings):
                request_data = module.process_request(request_data, settings)
                if hasattr(module, 'update_settings'):
                    updated = module.update_settings(settings)
                    if updated:
                        settings.update(updated)
        # Forward to OpenAI API using the client
        if request_data.get('stream', False):
            # Handle streaming response
            stream = openai_client.completions.create(**request_data)
            def generate():
                for chunk in stream:
                    yield f"data: {chunk.model_dump_json()}\n\n"
                yield "data: [DONE]\n\n"
            return app.response_class(
                generate(),
                mimetype='text/plain',
                headers={'Content-Type': 'text/event-stream'}
            )
        else:
            # Handle regular response
            response = openai_client.completions.create(**request_data)
            response_data = response.model_dump()
            # Process response through modules, allowing modules to update settings
            for module in module_manager.modules:
                if module.is_enabled(settings):
                    response_data = module.process_response(response_data, settings)
                    if hasattr(module, 'update_settings'):
                        updated = module.update_settings(settings)
                        if updated:
                            settings.update(updated)
            return jsonify(response_data), 200
    
    except Exception as e:
        logger.error(f"Error in completions: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    health_data = {
        'status': 'healthy',
        'llm_configured': bool(OPENAI_API_KEY),
        'llm_base_url': OPENAI_BASE_URL,
        'modules_loaded': len(module_manager.modules),
        'llm_alive': False,
        'llm_error': None,
        'debug_info': {}
    }
    
    # Test if the LLM is actually reachable
    if openai_client:
        try:
            # Use requests to test the connection directly with a short timeout
            import requests
            
            # Try to hit the models endpoint directly
            test_url = f"{OPENAI_BASE_URL}/models"
            headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
            
            logger.info(f"Testing LLM connection to: {test_url}")
            
            response = requests.get(test_url, headers=headers, timeout=2)
            
            # Add debug information
            health_data['debug_info'] = {
                'test_url': test_url,
                'status_code': response.status_code,
                'response_headers': dict(response.headers),
                'response_text': response.text[:200]  # First 200 chars
            }
            
            logger.info(f"LLM response: {response.status_code} - {response.text[:100]}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    health_data['llm_alive'] = True
                    health_data['llm_models_count'] = len(data.get('data', [])) if 'data' in data else 0
                    health_data['debug_info']['parsed_data'] = data
                except Exception as json_error:
                    health_data['llm_alive'] = False
                    health_data['llm_error'] = f"Invalid JSON response: {str(json_error)}"
                    health_data['status'] = 'degraded'
            else:
                health_data['llm_alive'] = False
                health_data['llm_error'] = f"HTTP {response.status_code}: {response.text[:100]}"
                health_data['status'] = 'degraded'
                
        except requests.exceptions.ConnectionError as e:
            health_data['llm_alive'] = False
            health_data['llm_error'] = f"Connection refused: {str(e)}"
            health_data['status'] = 'degraded'
            health_data['debug_info']['exception_type'] = 'ConnectionError'
        except requests.exceptions.Timeout as e:
            health_data['llm_alive'] = False
            health_data['llm_error'] = f"Connection timeout: {str(e)}"
            health_data['status'] = 'degraded'
            health_data['debug_info']['exception_type'] = 'Timeout'
        except Exception as e:
            health_data['llm_alive'] = False
            health_data['llm_error'] = f"Connection error: {str(e)}"
            health_data['status'] = 'degraded'
            health_data['debug_info']['exception_type'] = type(e).__name__
    else:
        health_data['llm_error'] = 'LLM client not configured'
        health_data['status'] = 'degraded'
    
    return jsonify(health_data)


# HTML Template for settings page
SETTINGS_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LLM Proxy Configuration</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Inter', sans-serif;
            line-height: 1.6;
            color: #1a1a1a;
            background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
            min-height: 100vh;
        }
        
        .header {
            background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
            color: white;
            padding: 2rem 0;
            text-align: center;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        }
        
        .header h1 {
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }
        
        .header p {
            opacity: 0.9;
            font-size: 1.1rem;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
        }
        
        .content-grid {
            display: grid;
            grid-template-columns: 1fr 350px;
            gap: 2rem;
            margin-top: -1rem;
        }
        
        .card {
            background: white;
            border-radius: 12px;
            padding: 2rem;
            box-shadow: 0 4px 25px rgba(0,0,0,0.08);
            border: 1px solid rgba(226, 232, 240, 0.8);
        }
        
        .card h2 {
            color: #1e293b;
            font-size: 1.4rem;
            font-weight: 600;
            margin-bottom: 1.5rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .modules-panel {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 2rem;
        }
        
        .modules-panel h3 {
            color: #475569;
            font-size: 1.1rem;
            margin-bottom: 1rem;
        }
        
        .module-item {
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            padding: 1rem;
            margin-bottom: 0.75rem;
        }
        
        .module-item:last-child {
            margin-bottom: 0;
        }
        
        .module-name {
            font-weight: 600;
            color: #334155;
            margin-bottom: 0.25rem;
        }
        
        .module-desc {
            color: #64748b;
            font-size: 0.9rem;
            line-height: 1.4;
        }
        
        .settings-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1.5rem;
        }
        
        .form-group {
            margin-bottom: 1.5rem;
        }
        
        .form-group label {
            display: block;
            font-weight: 600;
            color: #374151;
            margin-bottom: 0.5rem;
            text-transform: capitalize;
        }
        
        .form-group input,
        .form-group select {
            width: 100%;
            padding: 0.75rem;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            font-size: 0.95rem;
            transition: border-color 0.2s ease, box-shadow 0.2s ease;
            background: white;
        }
        
        .form-group input:focus,
        .form-group select:focus {
            outline: none;
            border-color: #3b82f6;
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
        }
        
        .checkbox-wrapper {
            display: flex;
            align-items: flex-start;
            gap: 0.75rem;
            padding: 0.75rem;
            background: #f9fafb;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            transition: border-color 0.2s ease;
        }
        
        .checkbox-wrapper:has(input:checked) {
            border-color: #10b981;
            background: #ecfdf5;
        }
        
        .checkbox-wrapper input[type="checkbox"] {
            width: auto;
            margin: 0;
            transform: scale(1.2);
        }
        
        .checkbox-label {
            color: #374151;
            font-size: 0.95rem;
            line-height: 1.4;
        }
        
        .field-description {
            color: #6b7280;
            font-size: 0.85rem;
            margin-top: 0.25rem;
            line-height: 1.4;
        }
        
        .button-group {
            display: flex;
            gap: 1rem;
            margin-top: 2rem;
            padding-top: 2rem;
            border-top: 1px solid #e5e7eb;
        }
        
        .btn {
            padding: 0.875rem 1.5rem;
            border: none;
            border-radius: 8px;
            font-size: 0.95rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .btn-primary {
            background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
            color: white;
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
        }
        
        .btn-primary:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 16px rgba(59, 130, 246, 0.4);
        }
        
        .btn-secondary {
            background: white;
            color: #374151;
            border: 2px solid #e5e7eb;
        }
        
        .btn-secondary:hover {
            border-color: #d1d5db;
            background: #f9fafb;
        }
        
        .message {
            margin-top: 1rem;
            padding: 1rem;
            border-radius: 8px;
            font-weight: 500;
        }
        
        .message.success {
            background: #ecfdf5;
            color: #065f46;
            border: 1px solid #a7f3d0;
        }
        
        .message.error {
            background: #fef2f2;
            color: #991b1b;
            border: 1px solid #fca5a5;
        }
        
        .api-info {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 1.5rem;
        }
        
        .api-info h3 {
            color: #475569;
            margin-bottom: 1.5rem;
            font-size: 1.1rem;
            font-weight: 600;
        }
        
        .api-endpoint {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            padding: 1rem;
            background: white;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            margin-bottom: 0.75rem;
            transition: box-shadow 0.2s ease;
        }
        
        .api-endpoint:hover {
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }
        
        .api-endpoint:last-child {
            margin-bottom: 0;
        }
        
        .endpoint-label {
            font-weight: 600;
            color: #374151;
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .endpoint-url {
            font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
            font-size: 0.8rem;
            color: #1e293b;
            background: #f8fafc;
            padding: 0.5rem 0.75rem;
            border-radius: 6px;
            border: 1px solid #e2e8f0;
            word-break: break-all;
            overflow-wrap: break-word;
        }
        
        .status-indicator {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 1rem;
            background: #ecfdf5;
            color: #065f46;
            border: 1px solid #a7f3d0;
            border-radius: 6px;
            font-size: 0.9rem;
            font-weight: 500;
        }
        
        .status-dot {
            width: 8px;
            height: 8px;
            background: #10b981;
            border-radius: 50%;
        }
        
        @media (max-width: 768px) {
            .content-grid {
                grid-template-columns: 1fr;
                gap: 1.5rem;
            }
            
            .container {
                padding: 1rem;
            }
            
            .settings-grid {
                grid-template-columns: 1fr;
            }
            
            .button-group {
                flex-direction: column;
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>LLM Proxy Configuration</h1>
        <p>Manage your AI proxy settings and modules</p>
    </div>
    
    <div class="container">
        <div class="card" style="margin-bottom: 2rem;">
            <h2>API Endpoints</h2>
            <div class="api-info">
                <div class="api-endpoint">
                    <span class="endpoint-label">Base URL</span>
                    <code class="endpoint-url">{{ request.url_root }}v1</code>
                </div>
                <div class="api-endpoint">
                    <span class="endpoint-label">Chat</span>
                    <code class="endpoint-url">POST /v1/chat/completions</code>
                </div>
                <div class="api-endpoint">
                    <span class="endpoint-label">Models</span>
                    <code class="endpoint-url">GET /v1/models</code>
                </div>
                <div class="api-endpoint">
                    <span class="endpoint-label">Health</span>
                    <code class="endpoint-url">GET /health</code>
                </div>
            </div>
        </div>
        
        <div class="content-grid">
            <div class="main-content">
                <div class="card">
                    <h2>Settings</h2>
                    
                    <form id="settingsForm">
                        <div class="settings-grid">
                            {% for setting in settings_schema %}
                                {% if setting.name not in ['default_model', 'llm_provider', 'response_format', 'max_tokens_limit', 'temperature_override'] %}
                                <div class="form-group">
                                    <label for="{{ setting.name }}">{{ setting.name.replace('_', ' ').replace('use ', '').title() }}</label>
                                    {% if setting.type == 'boolean' %}
                                        <div class="checkbox-wrapper">
                                            <input type="checkbox" 
                                                   id="{{ setting.name }}" 
                                                   name="{{ setting.name }}" 
                                                   {% if current_settings[setting.name] %}checked{% endif %}>
                                            <div class="checkbox-label">{{ setting.description }}</div>
                                        </div>
                                    {% elif setting.type == 'dropdown' %}
                                        <select id="{{ setting.name }}" name="{{ setting.name }}">
                                            {% for option in setting.options %}
                                                <option value="{{ option }}" 
                                                        {% if current_settings[setting.name] == option %}selected{% endif %}>
                                                    {{ option }}
                                                </option>
                                            {% endfor %}
                                        </select>
                                        <div class="field-description">{{ setting.description }}</div>
                                    {% else %}
                                        <input type="text" 
                                               id="{{ setting.name }}" 
                                               name="{{ setting.name }}" 
                                               value="{{ current_settings[setting.name] }}" 
                                               placeholder="{{ setting.default_value }}">
                                        <div class="field-description">{{ setting.description }}</div>
                                    {% endif %}
                                </div>
                                {% endif %}
                            {% endfor %}
                        </div>
                        
                        <div class="button-group">
                            <button type="submit" class="btn btn-primary">
                                Save Settings
                            </button>
                            <button type="button" class="btn btn-secondary" onclick="resetSettings()">
                                Reset Defaults
                            </button>
                        </div>
                    </form>
                    
                    <div id="message"></div>
                </div>
            </div>
            
            <div class="sidebar">
                <div class="card">
                    <h2>Modules</h2>
                    <div class="modules-panel">
                        {% for module in module_info %}
                        <div class="module-item">
                            <div class="module-name">{{ module.name.title() }}</div>
                            <div class="module-desc">{{ module.description }}</div>
                        </div>
                        {% endfor %}
                    </div>
                    
                    <div class="status-indicator">
                        <div class="status-dot"></div>
                        {{ module_info|length }} modules loaded
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        document.getElementById('settingsForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const formData = new FormData(this);
            const settings = {};
            
            {% for setting in settings_schema %}
                {% if setting.name not in ['default_model', 'llm_provider', 'response_format', 'max_tokens_limit', 'temperature_override'] %}
                    {% if setting.type == 'boolean' %}
                        settings['{{ setting.name }}'] = formData.has('{{ setting.name }}');
                    {% else %}
                        settings['{{ setting.name }}'] = formData.get('{{ setting.name }}') || '{{ setting.default_value }}';
                    {% endif %}
                {% endif %}
            {% endfor %}
            
            const messageDiv = document.getElementById('message');
            messageDiv.innerHTML = '';
            
            try {
                const response = await fetch('/api/settings', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(settings)
                });
                
                const result = await response.json();
                
                if (result.success) {
                    messageDiv.innerHTML = '<div class="message success">Settings saved successfully!</div>';
                } else {
                    messageDiv.innerHTML = '<div class="message error">Error saving settings: ' + result.message + '</div>';
                }
            } catch (error) {
                messageDiv.innerHTML = '<div class="message error">Error: ' + error.message + '</div>';
            }
        });
        
        function resetSettings() {
            if (confirm('Reset all settings to their default values?')) {
                location.reload();
            }
        }
    </script>
</body>
</html>
'''


if __name__ == '__main__':
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Starting OpenAI Proxy Server on {host}:{port}")
    logger.info(f"Settings page: http://{host}:{port}/")
    logger.info(f"API base URL: http://{host}:{port}/v1")
    
    app.run(host=host, port=port, debug=debug)
