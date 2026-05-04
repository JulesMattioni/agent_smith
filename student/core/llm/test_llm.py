import dotenv
from clients import OpenRouterClient


def main():
    dotenv.load_dotenv()

    client = OpenRouterClient(
        model_name="google/gemma-4-31b-it:free",
        base_url="https://openrouter.ai/api/v1",
        provider_name="openrouter",
    )

    messages = [{"role": "user", "content": "Say hello"}]
    response = client.generate(messages)
    print(response)


if __name__ == "__main__":
    main()