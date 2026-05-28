from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.models.models import User, Subscription, PlanType
from app.routes.auth import get_current_user
import httpx, hmac, hashlib, os, json
from datetime import datetime, timezone

router = APIRouter()

PADDLE_API_KEY      = os.getenv("PADDLE_API_KEY", "")
PADDLE_WEBHOOK_SECRET = os.getenv("PADDLE_WEBHOOK_SECRET", "")
FRONTEND_URL        = os.getenv("FRONTEND_URL", "http://localhost:3000")

# Paddle Price IDs — создаёшь в Paddle Dashboard → Catalog → Products
PADDLE_PRICES = {
    "business":   os.getenv("PADDLE_PRICE_BUSINESS",   "pri_xxx"),
    "enterprise": os.getenv("PADDLE_PRICE_ENTERPRISE",  "pri_xxx"),
}

PADDLE_API_BASE = "https://api.paddle.com"


# ── 1. Создать checkout-ссылку ────────────────────────────────────────────────

@router.post("/create-checkout")
async def create_checkout(
    plan: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if plan not in PADDLE_PRICES:
        raise HTTPException(400, "Неизвестный тариф")
    if not PADDLE_API_KEY:
        raise HTTPException(503, "Платёжная система не настроена")

    price_id = PADDLE_PRICES[plan]

    payload = {
        "items": [{"price_id": price_id, "quantity": 1}],
        "customer": {"email": current_user.email},
        "custom_data": {"user_id": current_user.id, "plan": plan},
        "success_url": f"{FRONTEND_URL}/success",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{PADDLE_API_BASE}/transactions",
            headers={
                "Authorization": f"Bearer {PADDLE_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

    if resp.status_code != 200:
        raise HTTPException(502, f"Paddle error: {resp.text}")

    data = resp.json().get("data", {})
    checkout_url = data.get("checkout", {}).get("url")

    if not checkout_url:
        raise HTTPException(502, "Paddle не вернул checkout URL")

    return {"checkout_url": checkout_url}


# ── 2. Webhook от Paddle ──────────────────────────────────────────────────────

def _verify_paddle_signature(body: bytes, signature_header: str) -> bool:
    """Верификация подписи по алгоритму Paddle (HMAC-SHA256)."""
    if not PADDLE_WEBHOOK_SECRET or not signature_header:
        return False

    # Формат заголовка: ts=...;h1=...
    parts = dict(p.split("=", 1) for p in signature_header.split(";") if "=" in p)
    ts    = parts.get("ts", "")
    h1    = parts.get("h1", "")

    signed_payload = f"{ts}:{body.decode()}"
    expected = hmac.new(
        PADDLE_WEBHOOK_SECRET.encode(),
        signed_payload.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, h1)


@router.post("/webhook")
async def paddle_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    sig  = request.headers.get("Paddle-Signature", "")

    if not _verify_paddle_signature(body, sig):
        raise HTTPException(400, "Невалидная подпись webhook")

    event = json.loads(body)
    event_type = event.get("event_type", "")
    data       = event.get("data", {})

    # ── Подписка создана / активирована ──────────────────────────────────────
    if event_type == "subscription.activated":
        _handle_subscription_activated(db, data)

    # ── Подписка обновлена (смена плана) ─────────────────────────────────────
    elif event_type == "subscription.updated":
        _handle_subscription_updated(db, data)

    # ── Подписка отменена ────────────────────────────────────────────────────
    elif event_type in ("subscription.canceled", "subscription.past_due"):
        _handle_subscription_canceled(db, data)

    # ── Платёж прошёл (на всякий случай активируем) ──────────────────────────
    elif event_type == "transaction.completed":
        custom = data.get("custom_data") or {}
        if custom.get("user_id") and custom.get("plan"):
            _activate_plan(db, custom["user_id"], custom["plan"],
                           data.get("subscription_id"))

    return {"received": True}


# ── Хелперы для обработки событий ────────────────────────────────────────────

def _activate_plan(db: Session, user_id: str, plan_str: str, paddle_sub_id: str | None):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return

    try:
        plan = PlanType(plan_str)
    except ValueError:
        plan = PlanType.business

    user.plan = plan

    sub = db.query(Subscription).filter(Subscription.user_id == user_id).first()
    if sub:
        sub.paddle_sub_id = paddle_sub_id
        sub.plan          = plan
        sub.status        = "active"
    else:
        sub = Subscription(
            user_id       = user_id,
            plan          = plan,
            paddle_sub_id = paddle_sub_id,
            status        = "active",
        )
        db.add(sub)

    db.commit()


def _handle_subscription_activated(db: Session, data: dict):
    custom = data.get("custom_data") or {}
    user_id      = custom.get("user_id")
    plan_str     = custom.get("plan", "business")
    paddle_sub_id = data.get("id")

    if user_id:
        _activate_plan(db, user_id, plan_str, paddle_sub_id)


def _handle_subscription_updated(db: Session, data: dict):
    paddle_sub_id = data.get("id")
    sub = db.query(Subscription).filter(
        Subscription.paddle_sub_id == paddle_sub_id
    ).first()
    if not sub:
        return

    # Получаем новый plan из items[0].price.custom_data или оставляем старый
    items = data.get("items", [])
    if items:
        custom = items[0].get("price", {}).get("custom_data") or {}
        new_plan = custom.get("plan")
        if new_plan:
            try:
                sub.plan = PlanType(new_plan)
                user = db.query(User).filter(User.id == sub.user_id).first()
                if user:
                    user.plan = PlanType(new_plan)
            except ValueError:
                pass

    next_billed = data.get("next_billed_at")
    if next_billed:
        sub.current_period_end = datetime.fromisoformat(
            next_billed.replace("Z", "+00:00")
        )

    db.commit()


def _handle_subscription_canceled(db: Session, data: dict):
    paddle_sub_id = data.get("id")
    sub = db.query(Subscription).filter(
        Subscription.paddle_sub_id == paddle_sub_id
    ).first()
    if not sub:
        return

    sub.status = "canceled"
    user = db.query(User).filter(User.id == sub.user_id).first()
    if user:
        user.plan = PlanType.free

    db.commit()


# ── 3. Текущая подписка пользователя ─────────────────────────────────────────

@router.get("/subscription")
def get_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sub = db.query(Subscription).filter(
        Subscription.user_id == current_user.id
    ).first()
    return {
        "plan":       current_user.plan,
        "status":     sub.status if sub else "free",
        "period_end": sub.current_period_end if sub else None,
    }


# ── 4. Портал управления подпиской (Paddle Customer Portal) ──────────────────

@router.post("/customer-portal")
async def customer_portal(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Возвращает ссылку на Paddle-портал, где юзер сам управляет подпиской."""
    sub = db.query(Subscription).filter(
        Subscription.user_id == current_user.id
    ).first()

    if not sub or not sub.paddle_sub_id:
        raise HTTPException(404, "Активная подписка не найдена")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{PADDLE_API_BASE}/subscriptions/{sub.paddle_sub_id}",
            headers={"Authorization": f"Bearer {PADDLE_API_KEY}"},
        )

    if resp.status_code != 200:
        raise HTTPException(502, "Не удалось получить данные подписки")

    portal_url = (
        resp.json()
        .get("data", {})
        .get("management_urls", {})
        .get("update_payment_method")
    )

    return {"portal_url": portal_url}
