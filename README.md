# LLM-itM

A lightweight proxy server that sits between your applications and LLM APIs (Ollama, OpenAI, etc.), providing configurable request/response processing modules and a web-based configuration interface.

## Purpose

This tool allows you to:
- Add custom processing to LLM requests/responses (logging, content filtering, etc.)
- Switch between different LLM providers without changing your application code
- Configure and monitor LLM interactions through a web interface
- Maintain OpenAI API compatibility while adding custom functionality

## Installation & Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure LLM Provider** (choose one):

   **For Ollama (default):**
   ```bash
   # Install Ollama from https://ollama.ai/
   ollama pull llama3.1  # Download a model
   ```

   **For OpenAI:**
   ```bash
   # Set environment variables
   export OPENAI_API_KEY=your_api_key_here
   export OPENAI_BASE_URL=https://api.openai.com/v1
   ```

3. **Run the Server**:
   ```bash
   python app.py
   ```

4. **Configure Settings**:
   - Open `http://localhost:5000` in your browser
   - Enable/disable modules and adjust settings as needed

## Usage

Point your applications to the proxy instead of the LLM directly:

**Base URL:** `http://localhost:5000/v1`

**Example with OpenAI Python library:**
```python
import openai

client = openai.OpenAI(
    api_key="your_api_key",  # or "ollama" for local Ollama
    base_url="http://localhost:5000/v1"
)

response = client.chat.completions.create(
    model="gpt-3.5-turbo",  # or "llama3.1" for Ollama
    messages=[{"role": "user", "content": "Hello!"}]
)
```

## Example Modules

- **Request Logging**: Log all API interactions for debugging
- **Content Moderation**: Filter inappropriate content in requests/responses  
- **Response Filtering**: Modify requests (temperature, max tokens, system prompts)

## API Endpoints

- `GET /` - Web configuration interface
- `POST /v1/chat/completions` - Chat completions (OpenAI compatible)
- `GET /v1/models` - List available models
- `GET /health` - Health check

## Configuration

Settings are automatically saved to `config.json` and can be modified through the web interface at `http://localhost:5000`.
