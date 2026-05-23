from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.models.models import User
from app.routes.auth import get_current_user
from pydantic import BaseModel

router = APIRouter()

class UpdateProfileIn(BaseModel):
    name: str | None = None

@router.get("/me")
def get_profile(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "plan": current_user.plan,
        "created_at": current_user.created_at,
    }

@router.patch("/me")
def update_profile(
    data: UpdateProfileIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if data.name:
        current_user.name = data.name
    db.commit()
    db.refresh(current_user)
    return {"message": "Профиль обновлён", "name": current_user.name}

@router.delete("/me")
def delete_account(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db.delete(current_user)
    db.commit()
    return {"message": "Аккаунт удалён"}
