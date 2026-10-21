import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')
DATA_DIR = BASE_DIR / 'data'
DATA_DIR.mkdir(exist_ok=True)
DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{DATA_DIR / "demo.db"}')
AGENTS_URL = os.getenv('AGENTS_URL', 'http://127.0.0.1:8002').rstrip('/')
RAG_URL = os.getenv('RAG_URL', 'http://127.0.0.1:8001').rstrip('/')
AGENTS_MODE = os.getenv('AGENTS_MODE', 'http')
SERVICE_TIMEOUT = float(os.getenv('SERVICE_TIMEOUT', '5'))
CORS_ORIGINS = os.getenv('CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(',')
