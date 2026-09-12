# Standardize on strict json_schema for the real service because it
# constrains the model to the required fields and makes validation
# deterministic. Use json_object only as a fallback if the model does
# not support strict JSON Schema; tool calling is unnecessary here.
from basic_chat_completion import client
import json


def match_toy_schema(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"topic", "urgency"}
        and isinstance(value['topic'], str)
        and isinstance(value['urgency'], str)
    )


toy_schema = {
    "type": "object",
    "properties": {
        "topic": {"type": "string"},
        "urgency": {"type": "string"},
    },
    "required": ["topic", "urgency"],
    "additionalProperties": False,
}

for attempt in range(5):
    completion = client.chat.completions.create(
        model='openai/gpt-oss-20b',
        messages=[
            {
                "role": "system",
                "content": "Return only JSON with topic and urgency.",
            },
            {
                "role": "user",
                "content": "My order arrived damaged.",
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "support_ticket",
                "strict": True,
                "schema": toy_schema
            }
        }
    )
    content = completion.choices[0].message.content
    toy = json.loads(content)

    assert match_toy_schema(toy), f"Invalid response: {toy}"
    print(f"Attempt {attempt + 1}: valid -> {toy}")


print("All 5 responses matched the toy schema.")
