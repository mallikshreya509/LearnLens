import os

# Tests never call the real Gemini API.
os.environ["LEARNLENS_MOCK"] = "1"
