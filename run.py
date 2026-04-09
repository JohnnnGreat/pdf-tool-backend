import uvicorn
from app.core.config import settings
from app import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "run:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
        reload_dirs=["app"],
    )
