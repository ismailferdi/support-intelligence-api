from basic_chat_completion import client

pricing = {
    "openai/gpt-oss-20b": {
        "input": 0.00003,
        "output": 0.00013
    }
}

def estimate_cost(prompt_tokens: int, completion_tokens: int, model: str) -> float:
    input_cost = (prompt_tokens / 1000) * pricing[model]["input"]
    output_cost = (completion_tokens / 1000) * pricing[model]["output"]
    total_cost = input_cost + output_cost
    return total_cost



completion = client.chat.completions.create(
    model="openai/gpt-oss-20b",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What should I do if my order arrives damaged?"},
    ],
    max_tokens=100,
)

usage = completion.usage

cost = estimate_cost(
    prompt_tokens=usage.prompt_tokens,
    completion_tokens=usage.completion_tokens,
    model="openai/gpt-oss-20b",
)

print(f"Prompt tokens: {usage.prompt_tokens}")
print(f"Completion tokens: {usage.completion_tokens}")
print(f"Total tokens: {usage.total_tokens}")
print(f"Estimated cost: ${cost:.8f}")

