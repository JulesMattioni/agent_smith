import dotenv
from clients import OpenRouterClient


def main():
    dotenv.load_dotenv()

    client = OpenRouterClient(
        model_name="google/gemma-4-26b-a4b-it:free",
        base_url="https://openrouter.ai/api/v1",
        provider_name="openrouter",
    )

    messages = [{"role": "user", "content": "Say hello"}]
    response = client.generate(messages)
    print(response)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(e)