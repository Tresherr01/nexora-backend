from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.models.models import WaitlistEntry
from pydantic import BaseModel, EmailStr

router = APIRouter()

class WaitlistIn(BaseModel):
    email: EmailStr
    source: str = "landing"

@router.post("/join")
def join_waitlist(data: WaitlistIn, db: Session = Depends(get_db)):
    if db.query(WaitlistEntry).filter(WaitlistEntry.email == data.email).first():
        return {"message": "Вы уже в списке!", "already_exists": True}
    entry = WaitlistEntry(email=data.email, source=data.source)
    db.add(entry)
    db.commit()
    return {"message": "Добавлено! Мы напишем когда откроем доступ.", "already_exists": False}

@router.get("/count")
def waitlist_count(db: Session = Depends(get_db)):
    return {"count": db.query(WaitlistEntry).count()}

@router.get("/list")
def waitlist_list(db: Session = Depends(get_db)):
    # Только для админа — добавь проверку в продакшне
    entries = db.query(WaitlistEntry).order_by(WaitlistEntry.created_at.desc()).all()
    return [{"email": e.email, "source": e.source, "date": e.created_at} for e in entries]
