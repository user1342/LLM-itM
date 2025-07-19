import os
import json
import logging
import uuid
import time
import copy
import argparse
from typing import Dict, Any

import openai
from flask import Flask, request, jsonify, render_template_string, redirect, url_for
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv

from config_manager import ConfigManager
from request_monitor import request_monitor

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='LLM Proxy Server')
    parser.add_argument('--host', 
                        default='http://localhost:11434/v1',
                        help='LLM API base URL (default: http://localhost:11434/v1 for Ollama)')
    parser.add_argument('--api-key',
                        default=None,
                        help='API key for the LLM service (default: None for Ollama)')
    parser.add_argument('--listen-host',
                        default='0.0.0.0',
                        help='Host to bind the proxy server to (default: 0.0.0.0)')
    parser.add_argument('--listen-port',
                        type=int,
                        default=5000,
                        help='Port to bind the proxy server to (default: 5000)')
    parser.add_argument('--debug',
                        action='store_true',
                        help='Enable debug mode')
    return parser.parse_args()


# Parse command line arguments
args = parse_arguments()

# Load environment variables (still load for other potential settings)
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize managers
config_manager = ConfigManager()
module_manager = config_manager.module_manager  # Get module manager from config manager

# Connect SocketIO to request monitor
request_monitor.set_socketio(socketio)

# Configure logging
logging.basicConfig(
    level=getattr(logging, config_manager.get_setting('log_level', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# LLM API Configuration from command line arguments
OPENAI_API_KEY = args.api_key or 'ollama'
OPENAI_BASE_URL = args.host

if not args.api_key and 'openai' in args.host.lower():
    logger.warning("No API key provided for OpenAI-like service. This may cause authentication errors.")

logger.info(f"LLM API Configuration:")
logger.info(f"  Base URL: {OPENAI_BASE_URL}")
logger.info(f"  API Key: {'Set' if args.api_key else 'None (using Ollama mode)'}")

openai_client = openai.OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL
)


def get_openai_client(request_headers=None):
    """Get OpenAI client with API key from request headers or default"""
    # Try to extract API key from Authorization header
    request_api_key = None
    if request_headers:
        auth_header = request_headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            request_api_key = auth_header.replace('Bearer ', '')
            logger.debug(f"Using API key from request headers")
        elif auth_header.startswith('sk-'):  # Direct API key in Authorization header
            request_api_key = auth_header
            logger.debug(f"Using API key from request headers (direct)")
    
    # Use request API key if provided, otherwise use default
    api_key = request_api_key if request_api_key else OPENAI_API_KEY
    
    # If we're using a different API key than default, create new client
    if request_api_key and request_api_key != OPENAI_API_KEY:
        logger.info(f"Creating client with request-specific API key")
        return openai.OpenAI(
            api_key=api_key,
            base_url=OPENAI_BASE_URL
        )
    
    # Use default client
    return openai_client


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


@app.route('/monitor')
def monitor_page():
    """Live request monitoring page"""
    return render_template_string(MONITOR_TEMPLATE)


@app.route('/api/monitor/records')
def get_monitor_records():
    """API endpoint to get monitoring records"""
    limit = request.args.get('limit', type=int)
    return jsonify(request_monitor.get_records(limit))


@app.route('/api/monitor/records/<record_id>')
def get_monitor_record(record_id):
    """API endpoint to get a specific monitoring record"""
    record = request_monitor.get_record(record_id)
    if record:
        return jsonify(record)
    return jsonify({'error': 'Record not found'}), 404


@app.route('/api/monitor/clear', methods=['POST'])
def clear_monitor_records():
    """API endpoint to clear all monitoring records"""
    request_monitor.clear_records()
    return jsonify({'success': True})


# WebSocket handlers
@socketio.on('connect')
def handle_connect():
    print('Client connected')


@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')


@app.route('/v1/models', methods=['GET'])
def list_models():
    """OpenAI API: List available models"""
    try:
        client = get_openai_client(request.headers)
        models = client.models.list()
        return jsonify(models.model_dump()), 200
    
    except Exception as e:
        logger.error(f"Error listing models: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    """OpenAI API: Chat completions endpoint"""
    start_time = time.time()
    request_id = str(uuid.uuid4())
    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', 
                                   request.environ.get('HTTP_X_REAL_IP', 
                                                     request.remote_addr))
    
    try:
        settings = config_manager.get_all_settings()
        original_request = copy.deepcopy(request.json)
        request_data = copy.deepcopy(original_request)
        
        # Get client with request-specific API key if provided
        client = get_openai_client(request.headers)
        
        request_monitor.start_request(
            request_id, client_ip, 'POST', '/v1/chat/completions',
            original_request, original_request
        )
        
        for module in module_manager.modules:
            if module.is_enabled(settings):
                request_data = module.process_request(request_data, settings)
                if hasattr(module, 'update_settings'):
                    updated = module.update_settings(settings)
                    if updated:
                        settings.update(updated)
        
        record = request_monitor._find_record(request_id)
        if record:
            record.processed_request = request_monitor._sanitize_data(copy.deepcopy(request_data))
        
        logger.info(f"Forwarding request to OpenAI: {request_data.get('model', 'unknown')}")
        
        if request_data.get('stream', False):
            stream = client.chat.completions.create(**request_data)
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
            response = client.chat.completions.create(**request_data)
            original_response = response.model_dump()
            response_data = copy.deepcopy(original_response)
            
            for module in module_manager.modules:
                if module.is_enabled(settings):
                    response_data = module.process_response(response_data, settings)
                    if hasattr(module, 'update_settings'):
                        updated = module.update_settings(settings)
                        if updated:
                            settings.update(updated)
            
            request_monitor.complete_request(
                request_id, original_response, response_data, start_time
            )
            
            return jsonify(response_data), 200
    
    except Exception as e:
        request_monitor.error_request(request_id, str(e), start_time)
        logger.error(f"Error in chat completions: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/v1/completions', methods=['POST'])
def completions():
    """OpenAI API: Text completions endpoint"""
    start_time = time.time()
    request_id = str(uuid.uuid4())
    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', 
                                   request.environ.get('HTTP_X_REAL_IP', 
                                                     request.remote_addr))
    
    try:
        settings = config_manager.get_all_settings()
        original_request = copy.deepcopy(request.json)
        request_data = copy.deepcopy(original_request)
        
        # Get client with request-specific API key if provided
        client = get_openai_client(request.headers)
        
        request_monitor.start_request(
            request_id, client_ip, 'POST', '/v1/completions',
            original_request, original_request
        )
        
        for module in module_manager.modules:
            if module.is_enabled(settings):
                request_data = module.process_request(request_data, settings)
                if hasattr(module, 'update_settings'):
                    updated = module.update_settings(settings)
                    if updated:
                        settings.update(updated)
        
        record = request_monitor._find_record(request_id)
        if record:
            record.processed_request = request_monitor._sanitize_data(copy.deepcopy(request_data))
        
        if request_data.get('stream', False):
            stream = client.completions.create(**request_data)
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
            response = client.completions.create(**request_data)
            original_response = response.model_dump()
            response_data = copy.deepcopy(original_response)
            
            for module in module_manager.modules:
                if module.is_enabled(settings):
                    response_data = module.process_response(response_data, settings)
                    if hasattr(module, 'update_settings'):
                        updated = module.update_settings(settings)
                        if updated:
                            settings.update(updated)
            
            request_monitor.complete_request(
                request_id, original_response, response_data, start_time
            )
            
            return jsonify(response_data), 200
    
    except Exception as e:
        request_monitor.error_request(request_id, str(e), start_time)
        logger.error(f"Error in completions: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    # Use API key from request headers if provided, otherwise use default
    client = get_openai_client(request.headers)
    # Extract the API key being used for the health check
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        request_api_key = auth_header.replace('Bearer ', '')
    elif auth_header.startswith('sk-'):
        request_api_key = auth_header
    else:
        request_api_key = OPENAI_API_KEY
    
    health_data = {
        'status': 'healthy',
        'llm_configured': bool(request_api_key),
        'llm_base_url': OPENAI_BASE_URL,
        'modules_loaded': len(module_manager.modules),
        'llm_alive': False,
        'llm_error': None,
        'debug_info': {}
    }
    
    try:
        import requests
        
        test_url = f"{OPENAI_BASE_URL}/models"
        headers = {"Authorization": f"Bearer {request_api_key}"}
        
        logger.info(f"Testing LLM connection to: {test_url}")
        
        response = requests.get(test_url, headers=headers, timeout=2)
        
        health_data['debug_info'] = {
            'test_url': test_url,
            'status_code': response.status_code,
            'response_headers': dict(response.headers),
            'response_text': response.text[:200]
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
    
    return jsonify(health_data)


# HTML Template for settings page
SETTINGS_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LLM-itM</title>
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
        <h1>LLM-itM</h1>
        <p>Manage your proxy settings and modules</p>
        <div style="margin-top: 1rem;">
            <a href="/monitor" style="color: white; text-decoration: none; background: rgba(255,255,255,0.2); padding: 0.5rem 1rem; border-radius: 6px; margin-right: 1rem;">Live Monitor</a>
            <a href="/" style="color: white; text-decoration: none; background: rgba(255,255,255,0.2); padding: 0.5rem 1rem; border-radius: 6px;">Settings</a>
        </div>
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


# Monitor Template
MONITOR_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LLM Proxy - Live Monitor</title>
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
            padding: 1.5rem 0;
            text-align: center;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        }
        
        .header h1 {
            font-size: 1.8rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }
        
        .nav-links {
            margin-top: 1rem;
        }
        
        .nav-links a {
            color: white;
            text-decoration: none;
            background: rgba(255,255,255,0.2);
            padding: 0.5rem 1rem;
            border-radius: 6px;
            margin: 0 0.5rem;
            transition: background 0.2s;
        }
        
        .nav-links a:hover {
            background: rgba(255,255,255,0.3);
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }
        
        .controls {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            background: white;
            padding: 1rem 2rem;
            border-radius: 12px;
            box-shadow: 0 4px 25px rgba(0,0,0,0.08);
        }
        
        .status {
            display: flex;
            align-items: center;
            gap: 1rem;
        }
        
        .status-indicator {
            display: flex;
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
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .clear-btn {
            padding: 0.75rem 1.5rem;
            background: #ef4444;
            color: white;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }
        
        .clear-btn:hover {
            background: #dc2626;
        }
        
        .requests-list {
            background: white;
            border-radius: 12px;
            box-shadow: 0 4px 25px rgba(0,0,0,0.08);
            overflow: hidden;
        }
        
        .request-item {
            border-bottom: 1px solid #e5e7eb;
            transition: background 0.2s;
        }
        
        .request-item:hover {
            background: #f9fafb;
        }
        
        .request-item:last-child {
            border-bottom: none;
        }
        
        .request-header {
            padding: 1.5rem;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .request-summary {
            display: flex;
            align-items: center;
            gap: 1rem;
        }
        
        .request-method {
            padding: 0.25rem 0.75rem;
            background: #3b82f6;
            color: white;
            border-radius: 4px;
            font-size: 0.8rem;
            font-weight: 600;
        }
        
        .request-info {
            flex: 1;
            min-width: 0;
        }
        
        .request-url {
            font-weight: 600;
            color: #1e293b;
            margin-bottom: 0.25rem;
        }
        
        .request-details {
            color: #64748b;
            font-size: 0.85rem;
        }
        
        .request-status {
            display: flex;
            align-items: center;
            gap: 1rem;
        }
        
        .status-badge {
            padding: 0.25rem 0.75rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }
        
        .status-pending {
            background: #fef3c7;
            color: #92400e;
        }
        
        .status-completed {
            background: #dcfce7;
            color: #166534;
        }
        
        .status-error {
            background: #fecaca;
            color: #991b1b;
        }
        
        .request-content {
            display: none;
            padding: 0 1.5rem 1.5rem;
            background: #f8fafc;
        }
        
        .request-content.expanded {
            display: block;
        }
        
        .content-section {
            margin-bottom: 2rem;
        }
        
        .content-section:last-child {
            margin-bottom: 0;
        }
        
        .content-title {
            font-weight: 600;
            color: #374151;
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid #e5e7eb;
        }
        
        .content-tabs {
            display: flex;
            gap: 1rem;
            margin-bottom: 1rem;
        }
        
        .tab-button {
            padding: 0.5rem 1rem;
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.85rem;
            font-weight: 500;
            color: #6b7280;
            transition: all 0.2s;
        }
        
        .tab-button.active {
            background: #3b82f6;
            color: white;
            border-color: #3b82f6;
        }
        
        .json-content {
            background: #1e293b;
            color: #e2e8f0;
            padding: 1.5rem;
            border-radius: 8px;
            font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
            font-size: 0.8rem;
            overflow-x: auto;
            white-space: pre;
            max-height: 400px;
            overflow-y: auto;
        }
        
        .empty-state {
            text-align: center;
            padding: 4rem 2rem;
            color: #6b7280;
        }
        
        .empty-state i {
            font-size: 3rem;
            margin-bottom: 1rem;
        }
        
        .loading {
            text-align: center;
            padding: 2rem;
            color: #6b7280;
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 1rem;
            }
            
            .controls {
                flex-direction: column;
                gap: 1rem;
            }
            
            .request-header {
                flex-direction: column;
                align-items: flex-start;
                gap: 1rem;
            }
            
            .request-summary {
                width: 100%;
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Live Request Monitor</h1>
        <p>Real-time monitoring of LLM proxy requests and responses</p>
        <div class="nav-links">
            <a href="/monitor">Live Monitor</a>
            <a href="/">Settings</a>
        </div>
    </div>
    
    <div class="container">
        <div class="controls">
            <div class="status">
                <div class="status-indicator">
                    <div class="status-dot"></div>
                    <span id="connection-status">Connecting...</span>
                </div>
                <div id="request-count">0 requests</div>
            </div>
            <button class="clear-btn" onclick="clearRecords()">Clear All Records</button>
        </div>
        
        <div class="requests-list" id="requests-list">
            <div class="loading">Loading requests...</div>
        </div>
    </div>

    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
    <script>
        let socket;
        let requests = [];
        let expandedRequests = new Set();
        
        // Initialize socket connection
        function initSocket() {
            socket = io();
            
            socket.on('connect', function() {
                document.getElementById('connection-status').textContent = 'Connected';
                loadInitialRequests();
            });
            
            socket.on('disconnect', function() {
                document.getElementById('connection-status').textContent = 'Disconnected';
            });
            
            socket.on('monitor_update', function(message) {
                handleMonitorUpdate(message);
            });
        }
        
        // Load initial requests
        async function loadInitialRequests() {
            try {
                const response = await fetch('/api/monitor/records?limit=50');
                const data = await response.json();
                requests = data;
                renderRequests();
            } catch (error) {
                console.error('Error loading requests:', error);
            }
        }
        
        // Handle real-time updates
        function handleMonitorUpdate(message) {
            const { type, data } = message;
            
            switch (type) {
                case 'request_started':
                    requests.unshift(data);
                    break;
                case 'request_completed':
                case 'request_error':
                    const index = requests.findIndex(r => r.id === data.id);
                    if (index >= 0) {
                        requests[index] = data;
                    }
                    break;
                case 'records_cleared':
                    requests = [];
                    expandedRequests.clear();
                    break;
            }
            
            renderRequests();
        }
        
        // Render requests list
        function renderRequests() {
            const container = document.getElementById('requests-list');
            const countElement = document.getElementById('request-count');
            
            countElement.textContent = `${requests.length} request${requests.length !== 1 ? 's' : ''}`;
            
            if (requests.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <div style="font-size: 3rem; margin-bottom: 1rem;">📡</div>
                        <h3>No requests yet</h3>
                        <p>Requests will appear here when they are received by the proxy</p>
                    </div>
                `;
                return;
            }
            
            container.innerHTML = requests.map(request => {
                const isExpanded = expandedRequests.has(request.id);
                return renderRequestItem(request, isExpanded);
            }).join('');
        }
        
        // Render individual request item
        function renderRequestItem(request, isExpanded) {
            const statusClass = `status-${request.status}`;
            const duration = request.duration_ms ? `${Math.round(request.duration_ms)}ms` : '-';
            const model = getModelFromRequest(request);
            
            return `
                <div class="request-item">
                    <div class="request-header" onclick="toggleRequest('${request.id}')">
                        <div class="request-summary">
                            <div class="request-method">${request.method}</div>
                            <div class="request-info">
                                <div class="request-url">${request.endpoint}</div>
                                <div class="request-details">
                                    ${request.datetime} • ${request.ip_address} • ${model} • ${duration}
                                </div>
                            </div>
                        </div>
                        <div class="request-status">
                            <div class="status-badge ${statusClass}">${request.status}</div>
                            <div>▼</div>
                        </div>
                    </div>
                    <div class="request-content ${isExpanded ? 'expanded' : ''}" id="content-${request.id}">
                        ${renderRequestContent(request)}
                    </div>
                </div>
            `;
        }
        
        // Render request content details
        function renderRequestContent(request) {
            return `
                <div class="content-section">
                    <div class="content-title">Request Data</div>
                    <div class="content-tabs">
                        <button class="tab-button active" onclick="showTab('${request.id}', 'original-req')">Original</button>
                        <button class="tab-button" onclick="showTab('${request.id}', 'processed-req')">After Modules</button>
                    </div>
                    <div id="tab-${request.id}-original-req" class="json-content">${formatJson(request.original_request)}</div>
                    <div id="tab-${request.id}-processed-req" class="json-content" style="display: none;">${formatJson(request.processed_request)}</div>
                </div>
                
                ${request.original_response ? `
                <div class="content-section">
                    <div class="content-title">Response Data</div>
                    <div class="content-tabs">
                        <button class="tab-button active" onclick="showTab('${request.id}', 'original-resp')">Original</button>
                        <button class="tab-button" onclick="showTab('${request.id}', 'processed-resp')">After Modules</button>
                    </div>
                    <div id="tab-${request.id}-original-resp" class="json-content">${formatJson(request.original_response)}</div>
                    <div id="tab-${request.id}-processed-resp" class="json-content" style="display: none;">${formatJson(request.processed_response)}</div>
                </div>
                ` : ''}
                
                ${request.error ? `
                <div class="content-section">
                    <div class="content-title">Error</div>
                    <div class="json-content" style="color: #ef4444;">${request.error}</div>
                </div>
                ` : ''}
            `;
        }
        
        // Toggle request expansion
        function toggleRequest(requestId) {
            const contentElement = document.getElementById(`content-${requestId}`);
            if (expandedRequests.has(requestId)) {
                expandedRequests.delete(requestId);
                contentElement.classList.remove('expanded');
            } else {
                expandedRequests.add(requestId);
                contentElement.classList.add('expanded');
            }
        }
        
        // Show specific tab
        function showTab(requestId, tabName) {
            // Hide all tabs for this request
            const tabs = document.querySelectorAll(`[id^="tab-${requestId}-"]`);
            tabs.forEach(tab => tab.style.display = 'none');
            
            // Show selected tab
            document.getElementById(`tab-${requestId}-${tabName}`).style.display = 'block';
            
            // Update button states
            const buttons = document.querySelectorAll(`#content-${requestId} .tab-button`);
            buttons.forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
        }
        
        // Format JSON for display
        function formatJson(obj) {
            if (!obj) return 'null';
            try {
                return JSON.stringify(obj, null, 2);
            } catch (e) {
                return String(obj);
            }
        }
        
        // Get model name from request
        function getModelFromRequest(request) {
            if (request.original_request && request.original_request.model) {
                return request.original_request.model;
            }
            return 'unknown';
        }
        
        // Clear all records
        async function clearRecords() {
            if (confirm('Clear all monitoring records?')) {
                try {
                    await fetch('/api/monitor/clear', { method: 'POST' });
                } catch (error) {
                    console.error('Error clearing records:', error);
                }
            }
        }
        
        // Initialize on page load
        document.addEventListener('DOMContentLoaded', function() {
            initSocket();
        });
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
    logger.info(f"Live Monitor: http://{host}:{port}/monitor")
    
    socketio.run(app, host=host, port=port, debug=debug)
