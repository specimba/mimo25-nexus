from langfuse import Langfuse
import os

langfuse = Langfuse(
    public_key=os.environ.get("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.environ.get("LANGFUSE_SECRET_KEY"),
    host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
)

def track_call(model, prompt, response, tokens):
    langfuse.trace(
        name="nexus-execution",
        input=prompt,
        output=response,
        metadata={"model": model, "tokens": tokens}
    )