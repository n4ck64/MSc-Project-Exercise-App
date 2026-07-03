import json
from ollama import chat


def structured_chat(model, system_prompt, user_message, schema, temperature=0.1):
    resp = chat(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}],
        format=schema,
        options={"temperature": temperature}
    )
    return json.loads(resp.message.content)
