import logging

from google import genai

from config import settings

logger = logging.getLogger("llm_client")

try:
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
except Exception as e:
    logger.error(f"Failed to initialize GenAI Client: {e}")
    client = None
