# Liste des modeles et provider associes a tester

- `--model-name meta-llama/llama-4-scout-17b-16e-instruct --provider-url https://api.groq.com/openai/v1`
- `--model-name llama-3.3-70b-versatile --provider-url https://api.groq.com/openai/v1`
- `--model-name qwen/qwen3-32b --provider-url https://api.groq.com/openai/v1`
- `--model-name qwen/qwen3-coder:free --provider-url https://openrouter.ai/api/v1`
- `--model-name gemma-4-26b-a4b-it --provider-url https://generativelanguage.googleapis.com/v1beta/openai`


## run command exemple

```bash
 uv run python -m agent_swebench \
  --task-file ../benchmark_outputs/scikit-learn__scikit-learn-13439/task.json \
  --output ../benchmark_outputs/scikit-learn__scikit-learn-13439/llama-4-scout-17b-16e-instruct.json \
  --model-name meta-llama/llama-4-scout-17b-16e-instruct \
  --provider-url https://api.groq.com/openai/v1
```