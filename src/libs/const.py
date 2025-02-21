import os

from dotenv import load_dotenv

load_dotenv()

GOOGLE_CLIENT_CONFIG = os.getenv("GOOGLE_CLIENT_CONFIG")
GOOGLE_CLIENT_ID = eval(GOOGLE_CLIENT_CONFIG)["web"]["client_id"]
GOOGLE_CLIENT_SECRET = eval(GOOGLE_CLIENT_CONFIG)["web"]["client_secret"]
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")
SECRET_KEY = os.getenv("SECRET_KEY")
POSTGRES_URL = os.getenv("POSTGRES_URL")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND")
STAGE = os.getenv("STAGE")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
XAI_API_KEY = os.getenv("XAI_API_KEY")
