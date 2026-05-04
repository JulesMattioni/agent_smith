import dotenv
from llm.clients import OpenRouterClient
from extractor.code_extractor import CodeExtractor


def main():
    dotenv.load_dotenv()
    # messages = [
    #     {
    #         "role": "system",
    #         "content": "You are a Python expert. Always respond with your solution inside a ```python code block.",
    #     },
    #     {
    #         "role": "user",
    #         "content": "Write a Python function called count_vowels that takes a string and returns the number of vowels (a,e,i,o,u), case insensitive.",
    #     },
    # ]

    messages = [
        {
            "role": "system",
            "content": """You are a coding assistant. You must respond using XML tool calls in this exact format:
    <invoke name="function_name">
    <parameter name="param1">value1</parameter>
    <parameter name="param2">value2</parameter>
    </invoke>

    Do not write any Python code blocks. Only use the XML format above.""",
        },
        {
            "role": "user",
            "content": "Call the read_file function with filepath='/testbed/file.py' and start_line=1 and end_line=50",
        },
    ]

    # try:
    #     print("=== Testing OpenRouterClient ===")
    #     client = OpenRouterClient(
    #         model_name="google/gemma-4-31b-it:free",
    #         provider_name="openrouter",
    #         base_url="https://openrouter.ai/api/v1",
    #     )
    #     response = client.generate(messages)
    #     print(response)
    # except Exception as e:
    #     print(e)

    try:
        print("\n=== Testing Groq Client ===")
        client = OpenRouterClient(
            model_name="qwen/qwen3-32b",
            provider_name="groq",
            base_url="https://api.groq.com/openai/v1",
        )
        response = client.generate(messages)
        print(CodeExtractor.extract(response.content))
    except Exception as e:
        print(e)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(e)
