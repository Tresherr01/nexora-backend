from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import auth, users, data, waitlist, payments

app = FastAPI(title="NEXORA API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшне — только твой домен
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,      prefix="/auth",     tags=["auth"])
app.include_router(users.router,     prefix="/users",    tags=["users"])
app.include_router(data.router,      prefix="/data",     tags=["data"])
app.include_router(waitlist.router,  prefix="/waitlist", tags=["waitlist"])
app.include_router(payments.router,  prefix="/payments", tags=["payments"])

@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}
