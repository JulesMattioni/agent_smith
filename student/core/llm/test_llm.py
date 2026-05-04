import dotenv
from clients import OpenRouterClient, GoogleClient


def main():
    dotenv.load_dotenv()
    messages = [{"role": "user", "content": "Say hello"}]

    # print("=== Testing OpenRouterClient ===")
    # client = OpenRouterClient(
    #     model_name="nousresearch/hermes-3-llama-3.1-405b:free",
    #     provider_name="openrouter",
    # )
    # response = client.generate(messages)
    # print(response)

    print("=== Testing GoogleClient ===")
    google = GoogleClient(
        model_name="models/gemini-2.0-flash-lite",
        provider_name="google"
    )
    response = google.generate(messages)
    print(response)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(e)