"""Run: python -m backend (from app root) or uvicorn backend.app.main:app"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8765, reload=True)
