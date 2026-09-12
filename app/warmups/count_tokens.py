import tiktoken

try:
    encoder = tiktoken.encoding_for_model('gpt-oss-20b')
except KeyError:
    encoder = tiktoken.get_encoding('o200k_harmony')

assert encoder.name == 'o200k_harmony'
print(f"Encoder name: {encoder.name}")


def count_tokens(text: str) -> int:
    tokens = encoder.encode(text)
    return len(tokens)


samples = [
    "",
    "Hello world",
    "My order arrived damaged.",
    "Please help me reset my account password"
]

for sample in samples:
    print(f"{sample!r}: {count_tokens(sample)} tokens")

assert count_tokens("") == 0
assert count_tokens("Hello world") > 0
assert count_tokens("My order arrived damaged.") >= 4
