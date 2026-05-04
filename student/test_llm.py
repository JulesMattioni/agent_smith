import dotenv
from core.llm.clients import OpenRouterClient
from core.agent.agent import Agent
from core.sandbox.sandbox import Sandbox
from core.sandbox.config import SandboxConfig


def main():
    dotenv.load_dotenv()

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

    system_prompt = """You are an autonomous coding agent. 
To solve the user's task, you must write Python code inside a ```python code block.
This code will be executed in a sandbox, and you will receive the standard output (Observation).
You can use `print()` to observe variables and results.
Once you have the final answer, call the function `final_answer("your result")`."""

    task = """Write a python script that does the following:
1. Import the 'os' module.
2. Print the current working directory using os.getcwd().
3. Call final_answer() with the result."""

    try:
        print("\n=== Testing Groq Agent ===")
        client = OpenRouterClient(
            model_name="qwen/qwen3-32b",
            provider_name="groq",
            base_url="https://api.groq.com/openai/v1",
        )
        config = SandboxConfig(max_execution_time_seconds=5)
        sandbox = Sandbox(config)
        agent = Agent(client, sandbox, 3)
        print(agent.run(task, system_prompt))
    except Exception as e:
        print(e)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(e)
