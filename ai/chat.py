from openai import OpenAI
def chat_with_ai(message, api_key, model):
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com"
    )
    response = client.chat.completions.create(
        model=model,
        messages=message
    )
    return response.choices[0].message.content