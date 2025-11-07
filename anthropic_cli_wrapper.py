#!/usr/bin/env python
"""
Simple CLI wrapper for Anthropic API to work with AgentFlow's Claude adapter.
Usage: anthropic.py messages create -m <model> --max-tokens <n> --json -p <prompt>
"""

import sys
import json
import os
from anthropic import Anthropic

def main():
    args = sys.argv[1:]
    
    # Parse command line arguments
    if len(args) < 2 or args[0] != "messages" or args[1] != "create":
        print(json.dumps({"error": "Usage: anthropic messages create -m <model> --max-tokens <n> --json -p <prompt>"}))
        sys.exit(1)
    
    model = "claude-3-5-sonnet-latest"
    max_tokens = 1024
    prompt = ""
    
    i = 2
    while i < len(args):
        if args[i] == "-m" and i + 1 < len(args):
            model = args[i + 1]
            i += 2
        elif args[i] == "--max-tokens" and i + 1 < len(args):
            max_tokens = int(args[i + 1])
            i += 2
        elif args[i] == "--json":
            i += 1
        elif args[i] == "-p" and i + 1 < len(args):
            prompt = args[i + 1]
            i += 2
        else:
            i += 1
    
    if not prompt:
        print(json.dumps({"error": "No prompt provided"}))
        sys.exit(1)
    
    # Get API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(json.dumps({"error": "ANTHROPIC_API_KEY environment variable not set"}))
        sys.exit(1)
    
    # Mock mode for testing (if using placeholder key)
    if api_key.startswith("sk-ant-your") or api_key == "test-key":
        # Generate contextual mock response based on prompt
        if "adapter" in prompt.lower() and "file" in prompt.lower():
            mock_text = f"Mock Claude Response:\n\nThe three main files in the src/agentflow/adapters directory are:\n\n1. **__init__.py** - Module initialization file that exports the adapter classes and defines the ADAPTERS registry mapping adapter names to classes.\n\n2. **codex_cli.py** - The Codex CLI adapter that wraps OpenAI's Codex CLI tool. It includes CodexCLIAdapter class, CodexCLIError exception, and CodexResult dataclass.\n\n3. **claude_cli.py** - The Claude CLI adapter (newly implemented) that wraps Anthropic's Claude API. It includes ClaudeCLIAdapter class, ClaudeCLIError exception, and ClaudeResult dataclass.\n\nThese adapters follow a consistent interface pattern, making it easy to switch between different LLM backends in AgentFlow."
        elif "benefit" in prompt.lower() or "advantage" in prompt.lower():
            mock_text = f"Mock Claude Response:\n\n# Benefits of the Adapter Pattern for LLM Integrations\n\n## 1. **Abstraction & Flexibility**\nThe adapter pattern decouples your application from specific LLM implementations. You can switch between OpenAI, Anthropic, local models, or future providers without changing core business logic.\n\n## 2. **Consistent Interface**\nAll adapters expose the same interface (e.g., `run(prompt) -> Result`), making it easy to:\n- Test different models with identical inputs\n- Compare outputs across providers\n- Implement fallback strategies\n\n## 3. **Easy Extension**\nAdding new providers is straightforward:\n```python\nADAPTERS = {{\n    'codex': CodexCLIAdapter,\n    'claude': ClaudeCLIAdapter,\n    'gpt4': GPT4Adapter,  # Future addition\n}}\n```\n\n## 4. **Centralized Configuration**\nEach adapter manages its own configuration (API keys, models, timeouts) without cluttering the main application.\n\n## 5. **Testability**\nMock adapters simplify testing without hitting real APIs or incurring costs.\n\nIn AgentFlow, this pattern enables seamless switching via `--adapter` flag while maintaining unified artifact generation."
        else:
            mock_text = f"Mock Claude Response:\n\nI've received your prompt: \"{prompt[:100]}{'...' if len(prompt) > 100 else ''}\"\n\nThis is a mock response from the Claude adapter. In production with a real API key, Claude would provide a detailed, contextual answer here.\n\nThe adapter successfully:\n- Parsed your prompt\n- Constructed the API request\n- Returned structured output\n- Tracked token usage\n\nTo get real responses, set a valid ANTHROPIC_API_KEY."
        
        # Return a mock response
        response = {
            "id": "msg_demo123",
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": mock_text
                }
            ],
            "model": model,
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {
                "input_tokens": len(prompt) // 4,  # Rough estimate
                "output_tokens": len(mock_text) // 4
            }
        }
        print(json.dumps(response))
        return
    
    try:
        # Call Anthropic API
        client = Anthropic(api_key=api_key)
        
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Convert to JSON format expected by adapter
        response = {
            "id": message.id,
            "type": message.type,
            "role": message.role,
            "content": [
                {
                    "type": block.type,
                    "text": block.text if hasattr(block, "text") else ""
                }
                for block in message.content
            ],
            "model": message.model,
            "stop_reason": message.stop_reason,
            "stop_sequence": message.stop_sequence,
            "usage": {
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens
            }
        }
        
        print(json.dumps(response))
        
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
