from pydantic import BaseModel


class LlmResponse(BaseModel):
    """Structured response returned by an LLM client."""

    input_tokens: int
    output_tokens: int
    content: str
    request_time_ms: float
    model_name: str
    attempts: int = 0
