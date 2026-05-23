from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.models.models import WaitlistEntry, Subscription, User, PlanType
from app.routes.auth import get_current_user
from pydantic import BaseModel, EmailStr
import stripe, os

router_waitlist = APIRouter()
router_payments = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

# Stripe Price IDs — создашь в Stripe Dashboard
STRIPE_PRICES = {
    "business": os.getenv("STRIPE_PRICE_BUSINESS", "price_xxx"),
}

# ── WAITLIST ──────────────────────────────────────────────────────────────────

class WaitlistIn(BaseModel):
    email: EmailStr
    source: str = "landing"

@router_waitlist.post("/join")
def join_waitlist(data: WaitlistIn, db: Session = Depends(get_db)):
    if db.query(WaitlistEntry).filter(WaitlistEntry.email == data.email).first():
        return {"message": "Вы уже в списке!", "already_exists": True}

    entry = WaitlistEntry(email=data.email, source=data.source)
    db.add(entry)
    db.commit()
    return {"message": "Добавлено! Мы напишем когда откроем доступ.", "already_exists": False}

@router_waitlist.get("/count")
def waitlist_count(db: Session = Depends(get_db)):
    count = db.query(WaitlistEntry).count()
    return {"count": count}

# ── PAYMENTS (Stripe) ─────────────────────────────────────────────────────────

@router_payments.post("/create-checkout")
def create_checkout(
    plan: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if plan not in STRIPE_PRICES:
        raise HTTPException(400, "Неизвестный тариф")

    session = stripe.checkout.Session.create(
        customer_email=current_user.email,
        payment_method_types=["card"],
        line_items=[{"price": STRIPE_PRICES[plan], "quantity": 1}],
        mode="subscription",
        success_url=os.getenv("FRONTEND_URL", "http://localhost:3000") + "/success?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=os.getenv("FRONTEND_URL", "http://localhost:3000") + "/pricing",
        metadata={"user_id": current_user.id, "plan": plan},
    )
    return {"checkout_url": session.url}


@router_payments.post("/webhook")
async def stripe_webhook(request_body: bytes, stripe_signature: str = None):
    """Stripe вызывает этот endpoint когда меняется статус подписки"""
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    try:
        event = stripe.Webhook.construct_event(request_body, stripe_signature, webhook_secret)
    except Exception:
        raise HTTPException(400, "Невалидный webhook")

    # Подписка активирована
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session["metadata"]["user_id"]
        plan    = session["metadata"]["plan"]
        # TODO: обновить план пользователя в БД
        # db.query(User).filter(User.id==user_id).update({"plan": plan})

    return {"received": True}


@router_payments.get("/subscription")
def get_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    return {
        "plan": current_user.plan,
        "subscription": {
            "status": sub.status if sub else None,
            "period_end": sub.current_period_end if sub else None,
        }
    }


# Экспортируем роутеры с правильными именами
from fastapi import APIRouter
waitlist_router = APIRouter()
waitlist_router.include_router(router_waitlist)

payments_router = APIRouter()
payments_router.include_router(router_payments)
