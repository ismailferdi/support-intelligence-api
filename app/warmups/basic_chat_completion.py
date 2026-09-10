import openai

client = openai.OpenAI(
    api_key="your_openai_api_key_here",
    base_url="https://integrate.api.nvidia.com/v1"
)

# try:
#     completion = client.chat.completions.create(
#         model='openai/gpt-oss-20b',
#         messages=[
#             {
#                 "role": "system",
#                 "content": "You are a helpful customer support assistant. Be concise and professional."
#             },
#             {
#                 "role": "user",
#                 "content": "My order arrived damaged. What should I do?"
#             }
#         ],
#         temperature=1,
#         top_p=1,
#         max_tokens=4096,
#         stream=False
#     )

#     print(f"The answer:\n{completion.choices[0].message.content} \n\n")
#     print(f"Pormpt tokens: {completion.usage.prompt_tokens}")
#     print(f"Completion tokens: {completion.usage.completion_tokens}")
#     print(f"Total tokens: {completion.usage.total_tokens}")
# except openai.APIError as exc:
#     print("Sorry, we're experiencing a temporary service problem. Please try again later.")