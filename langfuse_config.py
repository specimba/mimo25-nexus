from langfuse import Langfuse
import os

public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")

if not public_key:
    raise RuntimeError(
        "LANGFUSE_PUBLIC_KEY environment variable is required. "
        "Set it to enable telemetry; without it Langfuse init would silently drop traces."
    )
if not secret_key:
    raise RuntimeError(
        "LANGFUSE_SECRET_KEY environment variable is required. "
        "Set it to enable telemetry; without it Langfuse init would silently drop traces."
    )

langfuse = Langfuse(
    public_key=public_key,
    secret_key=secret_key,
    host=host
)

def track_call(model, prompt, response, tokens):
    langfuse.trace(
        name="nexus-execution",
        input=prompt,
        output=response,
        metadata={"model": model, "tokens": tokens}
    )