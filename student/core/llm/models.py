from pydantic import BaseModel


class LlmResponse(BaseModel):
    input_tokens: int
    output_tokens: int
    content: str
    request_time_ms: float
    model_name: str
