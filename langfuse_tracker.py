from langfuse import Langfuse
from datetime import datetime
import os

# Initialize once
public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")

if not public_key or not secret_key:
    raise RuntimeError(
        "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY environment variables are required. "
        "Set them to enable telemetry; without them Langfuse init would silently drop traces."
    )

langfuse = Langfuse(
    public_key=public_key,
    secret_key=secret_key,
    host=host
)

def track_model_call(provider, model, prompt, response, tokens_in, tokens_out, latency_ms):
    """Track any model call — works with OpenRouter, modelrelay, etc."""
    langfuse.trace(
        name=f"{provider}-{model}",
        input=prompt[:1000], # Truncate for privacy
        output=response[:1000],
        metadata={
            "provider": provider,
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": latency_ms,
            "timestamp": datetime.now().isoformat()
        },
        tags=[provider, "nexus-os"]
    )
    langfuse.flush() # Ensure sent

# Example usage with modelrelay:
def call_via_modelrelay(prompt, model="openai/gpt-4"):
    import time, requests

    start = time.time()
    response = requests.post(
        "https://your-modelrelay.com/v1/chat",
        json={"model": model, "messages": [{"role": "user", "content": prompt}]},
        headers={"Authorization": f"Bearer {os.getenv('MODELRELAY_KEY')}"}
    )
    latency = (time.time() - start) * 1000

    data = response.json()
    text = data["choices"][0]["message"]["content"]
    tokens_in = data["usage"]["prompt_tokens"]
    tokens_out = data["usage"]["completion_tokens"]

    # Track it
    track_model_call("modelrelay", model, prompt, text, tokens_in, tokens_out, latency)

    return text