#!/usr/bin/env python3
"""
Simple Interface for OpenAI Proxy Server
"""
import openai
import os

def main():
    """Simple chat interface"""
    print("LLM Proxy Chat (Ollama/OpenAI)")
    
    base_url = input("Enter base URL: ").strip()

    if len(base_url) < 1:
        base_url = 'http://localhost:5000/v1'
        print("Using default base URL: http://localhost:5000/v1")
    
    # Get API key (default to ollama for local usage)
    api_key = input("Enter API Key): ").strip()

    if len(api_key) < 1:
        api_key = ''


    # Get model (default to common Ollama model)
    model = input("Enter model name (e.g., llama3.1, gpt-3.5-turbo): ").strip()
    if not model:
        model = "llama3.1"
    
    # Configure OpenAI client to use the proxy
    client = openai.OpenAI(
        api_key=api_key,
        base_url=base_url
    )
    
    try:
        user_input = input("You: ").strip()
        # Send message
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": user_input}],
            temperature=0.7,
            max_tokens=1000
        )
        print(f"AI: {response.choices[0].message.content}\n")
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}\n")

if __name__ == "__main__":
    main()
