import json
import openai
from src.libs.const import OPENAI_API_KEY

client = openai.OpenAI(api_key=OPENAI_API_KEY)


def classify_email(email: list[str]):
    try:
        api_response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=20,
            top_p=0.1,
            messages=[
                {
                    "role": "system",
                    "content": """AI Instructions
Your only job is to classify the email the user has provided, and choose all applicable categories from the list.
Call the API function with all applicable categories as a list.
Only call the function. Do not include explanations or summaries.
If there's a problem (e.g., multiple unrelated emails or corrupted input), return ['error'].
Do not infer categories beyond those listed.""",
                },
                {"role": "user", "content": email},
            ],
            function_call={"name": "category_results"},
            functions=[
                {
                    "name": "category_results",
                    "description": "Reports all applicable email categories",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "category": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "enum": [
                                        "urgent",
                                        "actionable",
                                        "information",
                                        "newsletter",
                                        "promo",
                                        "other",
                                    ],
                                },
                                "description": "One or more categories",
                            },
                        },
                        "required": ["category"],
                    },
                }
            ],
        )
        func_call = api_response.choices[0].message.function_call
        args = json.loads(func_call.arguments)
        categories = args["category"]

        return categories, func_call

    # many more openai-specific error handlers can go here
    except Exception as err:
        error_message = f"API Error: {str(err)}"
        print(error_message)
        raise