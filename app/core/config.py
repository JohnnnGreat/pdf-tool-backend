from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_NAME: str = "DocForge API"
    DEBUG: bool = True
    SECRET_KEY: str = "change-me-in-production"
    PORT: int = 8000

    # Database
    DATABASE_URL: str = "sqlite:///./docforge.db"

    # Auth
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Generic manual webhook secret (keep for admin use)
    WEBHOOK_SECRET: str = "change-me-webhook-secret"

    # Payment providers
    PAYSTACK_SECRET_KEY: str = ""           # sk_live_xxx  (from Paystack dashboard)
    FLUTTERWAVE_SECRET_KEY: str = ""        # FLWSECK_xxx  (from Flutterwave dashboard)
    FLUTTERWAVE_SECRET_HASH: str = ""       # static hash you set in FW webhook settings
    LEMONSQUEEZY_WEBHOOK_SECRET: str = ""   # from LS Settings → Webhooks
    COINBASE_WEBHOOK_SECRET: str = ""       # from Coinbase Commerce → Settings → Webhooks

    # Payment callback (frontend URL — where provider redirects after payment)
    PAYMENT_CALLBACK_URL: str = "http://localhost:3000/dashboard/upgrade/success"

    # AI providers
    GEMINI_API_KEY: str = ""    # from Google AI Studio (aistudio.google.com)
    GROQ_API_KEY: str   = ""    # from console.groq.com

    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # File limits
    MAX_FILE_SIZE_MB: int = 50
    MAX_FILES_PER_REQUEST: int = 20
    TEMP_FILE_RETENTION_MINUTES: int = 60

    # Paths
    UPLOAD_DIR: str = "./uploads"
    OUTPUT_DIR: str = "./outputs"

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 30
    RATE_LIMIT_PER_HOUR: int = 200

    # OCR
    TESSERACT_PATH: str = ""
    TESSERACT_LANG: str = "eng"

    # LibreOffice
    LIBREOFFICE_PATH: str = ""

    # Redis (optional)
    REDIS_URL: str = ""

    # S3 (optional)
    S3_BUCKET: str = ""
    S3_REGION: str = ""
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""


settings = Settings()
