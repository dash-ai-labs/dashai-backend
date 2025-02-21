from typing import List

import numpy as np
from openai import OpenAI

from src.libs.const import OPENAI_API_KEY


def generate_embedding(text: str, model="text-embedding-3-small", **kwargs) -> List[float]:
    client = OpenAI(api_key=OPENAI_API_KEY)

    # replace newlines, which can negatively affect performance.
    text = text.replace("\n", " ")

    response = client.embeddings.create(input=[text], model=model, **kwargs)

    return response.data[0].embedding
