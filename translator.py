import os
import openai

openai.api_key = os.getenv("OPENAI_API_KEY")

PROMPT_SYSTEM = "You translate Chinese to English."


def check_api_key():
    if not openai.api_key:
        raise RuntimeError(
            "OPENAI_API_KEY environment variable not set. Please set it before running.")


def translate(text: str) -> str:
    """Translate Chinese text to English using OpenAI."""
    check_api_key()
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": PROMPT_SYSTEM},
            {"role": "user", "content": text},
        ],
    )
    return response.choices[0].message.content.strip()
