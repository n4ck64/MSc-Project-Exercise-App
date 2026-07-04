"""
All JSON and LLM structuring goes here. 
"""

import json
from ollama import chat


def structured_chat(model, system_prompt, user_message, schema, temperature=0.1):
    """
    Takes an LLM, its system prompt, the user's query and a predetermined JSON schema
    and instructs the LLM to return a JSON for function calling.
    """
    resp = chat(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}],
        format=schema,
        options={"temperature": temperature}
    )
    return json.loads(resp.message.content)
