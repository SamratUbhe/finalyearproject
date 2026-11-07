"""Convenience root runner to launch the Automated Code Vulnerability Reviewer."""

import sys
from pathlib import Path

root = Path(__file__).resolve().parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

if __name__ == "__main__":
    import uvicorn
    from src.core.config import get_settings

    settings = get_settings()
    print("=" * 60)
    print(" Automated Code Vulnerability Reviewer")
    print(f" Dashboard URL: http://{settings.host}:{settings.port}/dashboard")
    print(f" API Docs:      http://{settings.host}:{settings.port}/docs")
    print("=" * 60)
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=True if settings.app_env == "development" else False,
    )

