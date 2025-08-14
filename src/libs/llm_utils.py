import json
import openai
from src.libs.const import OPENAI_API_KEY

client = openai.OpenAI(api_key=OPENAI_API_KEY)

# need more diverse examples
multi_shot_examples = [
    # {
    #     "text": """We're happy to confirm you have completed your payment ABC12349567 of CAD C$120.00! 
    #     You don't need to do anything else, just allow 2-3 business days for us to process and deliver your payment 
    #     to OUAC . Your institution has access to your payment status on their Flywire Dashboard and can see that 
    #     your payment has been received. We shall notify you once the payment has been delivered. 
    #     You can view your payment details DOWNLOAD YOUR RECEIPT Thank you! 💡Did you know? 
    #     You can sign up to receive future offers and promotions from Flywire. Sign up here""",
    #     "categories": ["information"]
    # },
    {
        "text": """iCloud+ with 50 GB (Monthly) Renews August 29, 2025 $1.29 Billing and Payment 
        NS Canada Subtotal $1.29 GST/HST $0.18 Visa •••• 9999 $1.47 
        If you have any questions about your bill, please contact support. 
        This email confirms payment for the iCloud+ plan listed above. 
        You will be billed each plan period until you cancel by downgrading to the free storage plan from your 
        iOS device, Mac or PC. You may contact Apple for a full refund within 15 days of a monthly subscription 
        upgrade or within 45 days of a yearly payment. Partial refunds are available where required by law.""",
        "categories": ["information"]
    },
]

def classify_email(email: str):
    # Compose few-shot examples in prompt form
    example_text = ""
    for example in multi_shot_examples:
        example_text += f"Email:\n{example['text']}\nCategories: {example['categories']}\n\n"

    system_prompt = f"""
You are an AI assistant trained to classify emails into exactly one or more of these categories:

- urgent: Requires immediate attention from the user.
- actionable: Requires user action but not urgent.
- information: Informative only, no action required.
- newsletter: Regular updates or news sent periodically.
- promo: Promotional or marketing content.
- other: Does not fit any of the above categories.

Notes:
- 'urgent' and 'information' are mutually exclusive.
- 'actionable' and 'information' are mutually exclusive.
- 'promo' and 'information' are mutually exclusive.
- 'newsletter' and 'information' are mutually exclusive.

Classify the emails below into one or more categories from the list above.

Only output the categories as a JSON array.

If the email is corrupted or contains multiple unrelated emails, output ['error'].

Examples:

{example_text}

Now classify this email:
"""

    try:
        api_response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=40,
            temperature=0,   # deterministic output
            top_p=1,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": email},
            ],
            function_call={"name": "category_results"},
            functions=[
                {
                    "name": "category_results",
                    "description": "Reports the most applicable email category",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "category": {
                                "type": "string",
                                "enum": [
                                    "urgent",
                                    "actionable",
                                    "information",
                                    "newsletter",
                                    "promo",
                                    "other",
                                ],
                                "description": "One category",
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

    except Exception as e:
        return ["error"], str(e)