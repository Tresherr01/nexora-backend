from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.models.models import Dataset, ChatMessage, User, PlanType
from app.routes.auth import get_current_user
from pydantic import BaseModel
import pandas as pd
import anthropic
import io, os, json

router = APIRouter()
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Лимиты по тарифам
PLAN_LIMITS = {
    PlanType.free:       {"rows": 10_000,     "ai_questions": 50},
    PlanType.business:   {"rows": 10_000_000, "ai_questions": 999_999},
    PlanType.enterprise: {"rows": 999_999_999, "ai_questions": 999_999},
}

# ── Upload CSV ────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not file.filename.endswith((".csv", ".tsv")):
        raise HTTPException(400, "Только CSV и TSV файлы")

    content = await file.read()
    df = pd.read_csv(io.BytesIO(content))

    limit = PLAN_LIMITS[current_user.plan]["rows"]
    if len(df) > limit:
        raise HTTPException(403, f"Ваш тариф поддерживает до {limit:,} строк. Обновите план.")

    # Сохранить файл
    save_path = f"{UPLOAD_DIR}/{current_user.id}_{file.filename}"
    with open(save_path, "wb") as f:
        f.write(content)

    dataset = Dataset(
        user_id=current_user.id,
        name=file.filename,
        rows=len(df),
        columns=len(df.columns),
        size_bytes=len(content),
        storage_path=save_path,
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    return {
        "id": dataset.id,
        "name": dataset.name,
        "rows": dataset.rows,
        "columns": dataset.columns,
        "columns_list": df.columns.tolist(),
        "preview": df.head(5).to_dict(orient="records"),
    }


# ── List datasets ─────────────────────────────────────────────────────────────

@router.get("/datasets")
def list_datasets(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    datasets = db.query(Dataset).filter(Dataset.user_id == current_user.id).all()
    return [{"id": d.id, "name": d.name, "rows": d.rows, "columns": d.columns, "created_at": d.created_at} for d in datasets]


# ── AI Chat ───────────────────────────────────────────────────────────────────

class ChatIn(BaseModel):
    dataset_id: str
    message: str
    history: list[dict] = []

@router.post("/chat")
async def chat_with_data(
    body: ChatIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Проверить лимит вопросов
    limit = PLAN_LIMITS[current_user.plan]["ai_questions"]
    used = db.query(ChatMessage).filter(
        ChatMessage.user_id == current_user.id,
        ChatMessage.role == "user"
    ).count()
    if used >= limit:
        raise HTTPException(403, f"Вы исчерпали {limit} AI-вопросов на этом тарифе. Обновите план.")

    # Загрузить датасет
    dataset = db.query(Dataset).filter(
        Dataset.id == body.dataset_id,
        Dataset.user_id == current_user.id
    ).first()
    if not dataset:
        raise HTTPException(404, "Датасет не найден")

    df = pd.read_csv(dataset.storage_path)

    # Статистика
    num_cols = df.select_dtypes(include="number").columns.tolist()
    stats = df[num_cols].describe().to_string() if num_cols else "Числовых колонок нет"

    system_prompt = f"""Ты NEXORA AI — умный бизнес-аналитик. Отвечай на русском языке, кратко и конкретно.
Давай инсайты с числами. Выделяй паттерны. Будь как умный коллега, не как скучный отчёт.

ДАТАСЕТ: {dataset.name}
Строк: {len(df)}, Колонок: {len(df.columns)}
Колонки: {', '.join(df.columns.tolist())}

Статистика:
{stats}

Первые 10 строк:
{df.head(10).to_json(orient='records', force_ascii=False)}
"""

    # Собрать историю
    messages = body.history[-10:]  # Последние 10 сообщений для контекста
    messages.append({"role": "user", "content": body.message})

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=system_prompt,
        messages=messages,
    )

    answer = response.content[0].text
    tokens = response.usage.input_tokens + response.usage.output_tokens

    # Сохранить в историю
    db.add(ChatMessage(user_id=current_user.id, dataset_id=dataset.id, role="user",    content=body.message, tokens_used=0))
    db.add(ChatMessage(user_id=current_user.id, dataset_id=dataset.id, role="assistant", content=answer,       tokens_used=tokens))
    db.commit()

    return {"answer": answer, "tokens_used": tokens}
