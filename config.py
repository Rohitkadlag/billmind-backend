import os
import json
import tempfile
from dotenv import load_dotenv

load_dotenv()

if os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON'):
    creds_json = json.loads(os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON'))
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        json.dump(creds_json, f)
        GOOGLE_CREDENTIALS_PATH = f.name
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = f.name
else:
    GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "./google-key.json")
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = GOOGLE_CREDENTIALS_PATH

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
API_KEY = os.getenv("API_KEY", "billmind-secret-key-123")

required_vars = {
    "GOOGLE_CREDENTIALS_PATH": GOOGLE_CREDENTIALS_PATH,
    "OPENAI_API_KEY": OPENAI_API_KEY,
    "GOOGLE_SHEET_ID": GOOGLE_SHEET_ID,
    "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
    "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
    "API_KEY": API_KEY
}

for var_name, var_value in required_vars.items():
    if not var_value or var_value == "":
        print(f"⚠️  Warning: {var_name} is not set or empty in .env file")
