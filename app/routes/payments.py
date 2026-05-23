from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.models.models import User, Subscription, PlanType
from app.routes.auth import get_current_user
import stripe, os

router = APIRouter()
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

STRIPE_PRICES = {
    "business": os.getenv("STRIPE_PRICE_BUSINESS", "price_xxx"),
}

@router.post("/create-checkout")
def create_checkout(
    plan: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if plan not in STRIPE_PRICES:
        raise HTTPException(400, "Неизвестный тариф")
    if not stripe.api_key:
        raise HTTPException(503, "Платёжная система не настроена")

    session = stripe.checkout.Session.create(
        customer_email=current_user.email,
        payment_method_types=["card"],
        line_items=[{"price": STRIPE_PRICES[plan], "quantity": 1}],
        mode="subscription",
        success_url=os.getenv("FRONTEND_URL", "http://localhost:3000") + "/success",
        cancel_url=os.getenv("FRONTEND_URL", "http://localhost:3000") + "/pricing",
        metadata={"user_id": current_user.id, "plan": plan},
    )
    return {"checkout_url": session.url}


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    sig  = request.headers.get("stripe-signature", "")
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    try:
        event = stripe.Webhook.construct_event(body, sig, secret)
    except Exception:
        raise HTTPException(400, "Невалидный webhook")

    if event["type"] == "checkout.session.completed":
        meta    = event["data"]["object"]["metadata"]
        user_id = meta.get("user_id")
        plan    = meta.get("plan", "business")
        sub_id  = event["data"]["object"].get("subscription")

        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.plan = PlanType(plan)
            sub = Subscription(user_id=user_id, plan=PlanType(plan),
                               stripe_sub_id=sub_id, status="active")
            db.add(sub)
            db.commit()

    elif event["type"] == "customer.subscription.deleted":
        sub_id = event["data"]["object"]["id"]
        sub = db.query(Subscription).filter(Subscription.stripe_sub_id == sub_id).first()
        if sub:
            sub.status = "canceled"
            user = db.query(User).filter(User.id == sub.user_id).first()
            if user:
                user.plan = PlanType.free
            db.commit()

    return {"received": True}


@router.get("/subscription")
def get_subscription(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    return {
        "plan": current_user.plan,
        "status": sub.status if sub else "free",
        "period_end": sub.current_period_end if sub else None,
    }
