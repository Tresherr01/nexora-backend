from app.main import app
from app.models.database import create_tables

if __name__ == "__main__":
    create_tables()
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
