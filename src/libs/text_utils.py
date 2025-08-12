from openai import OpenAI

from src.libs.const import OPENAI_API_KEY


def summarize_text(content, name):
    client = OpenAI(api_key=OPENAI_API_KEY)

    try:
        response = client.chat.completions.create(
            model="gpt-5-nano",
            messages=[
                {
                    "role": "system",
                    "content": f"Summarize content you are provided to second grade reading level in active voice. Only the most important information is needed in 1 sentence (20 words). Refer to {name} as you or any variation of the active pronoun. Make sure everything is in active voice. If the email is 100% spam and only if you are completely certain about the spam, please start the response with '[Potential Spam]' and provide a reason.",
                },
                {"role": "user", "content": content},
            ],
            temperature=0.7,
            top_p=1,
        )
        return response.choices[0].message.content
    except Exception as e:
        return None
