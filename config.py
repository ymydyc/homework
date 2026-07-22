import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # LLM - DeepSeek
    DEEPSEEK_API_KEY = "sk-e036f25126ae44e087ed7043bcf73561"
    LLM_MODEL = "deepseek-chat"
    LLM_BASE_URL = "https://api.deepseek.com"
    
    # LLM - Qwen (备用)
    QWEN_API_KEY = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY", "")
    QWEN_MODEL = "qwen3.5-plus"
    QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # Flask
    HOST = os.getenv("FLASK_HOST", "127.0.0.1")
    PORT = int(os.getenv("FLASK_PORT", 5000))
    DEBUG = os.getenv("FLASK_DEBUG", "true").lower() == "true"

    # Data
    MAX_REVIEW_PAGES = int(os.getenv("MAX_REVIEW_PAGES", 10))
    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 15))
    REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", 1))

    # Paths
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(BASE_DIR, "data")
    CACHE_DIR = os.path.join(DATA_DIR, "cache")
    EXPORT_DIR = os.path.join(DATA_DIR, "exports")
    DB_PATH = os.path.join(DATA_DIR, "app.db")
