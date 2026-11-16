import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')
DATA_DIR = BASE_DIR / 'data'
DATA_DIR.mkdir(exist_ok=True)
RESOURCE_UPLOAD_DIR = Path(os.getenv('RESOURCE_UPLOAD_DIR', str(DATA_DIR / 'resource_files')))
if not RESOURCE_UPLOAD_DIR.is_absolute():
    RESOURCE_UPLOAD_DIR = BASE_DIR / RESOURCE_UPLOAD_DIR
DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'mysql+pymysql://root:123456@127.0.0.1:3306/learning_diagnosis?charset=utf8mb4',
)
RAG_URL = os.getenv('RAG_URL', 'http://127.0.0.1:8001').rstrip('/')
SERVICE_TIMEOUT = float(os.getenv('SERVICE_TIMEOUT', '5'))
CORS_ORIGINS = os.getenv('CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(',')
EMAIL_VERIFICATION_SECRET = os.getenv('EMAIL_VERIFICATION_SECRET', '')
SMTP_HOST = os.getenv('SMTP_HOST', '')
SMTP_PORT = int(os.getenv('SMTP_PORT', '465'))
SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
SMTP_FROM = os.getenv('SMTP_FROM', '') or SMTP_USERNAME
SMTP_SECURITY = os.getenv('SMTP_SECURITY', 'ssl').lower()
SMTP_TIMEOUT = float(os.getenv('SMTP_TIMEOUT', '10'))

# 内部服务使用独立密钥和课程白名单；留空默认不可访问，不复用用户登录 Token。
C_SERVICE_KEY = os.getenv('C_SERVICE_KEY', '')
D_SERVICE_KEY = os.getenv('D_SERVICE_KEY', '')
C_SERVICE_COURSE_IDS = os.getenv('C_SERVICE_COURSE_IDS', '')
D_SERVICE_COURSE_IDS = os.getenv('D_SERVICE_COURSE_IDS', '')

# 测验结算只写持久化任务；独立 worker 提交事务后再通知 D。
DIAGNOSIS_AUTO_ENQUEUE = os.getenv('DIAGNOSIS_AUTO_ENQUEUE', 'true').lower() in ('true', '1', 'yes')
DIAGNOSIS_URL = os.getenv('DIAGNOSIS_URL', 'http://127.0.0.1:8002').rstrip('/')
DIAGNOSIS_SERVICE_KEY = os.getenv('DIAGNOSIS_SERVICE_KEY', '')
DIAGNOSIS_TIMEOUT = float(os.getenv('DIAGNOSIS_TIMEOUT', '10'))
DIAGNOSIS_MAX_ATTEMPTS = int(os.getenv('DIAGNOSIS_MAX_ATTEMPTS', '5'))
