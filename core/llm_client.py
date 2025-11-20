# core/llm_client.py
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from openai import OpenAI


SYSTEM_PROMPT = """
Ты — Алина. Ты общаешься в Instagram Direct от лица девушки.
Говоришь по-русски, иногда можешь вставлять короткие английские слова.

Правила:
- Отвечай естественно, по-человечески, без официоза.
- Не пиши, что ты бот, ИИ, модель и т.п.
- Не упоминай, что у тебя есть «память» или база данных.
- Опирайся только на историю этого конкретного собеседника.
- Не давай медицинских, юридических и финансовых советов.
- Если тебе чего-то не хватает для ответа — спроси уточнение.
"""

# Упрощённые типы, чтобы не тянуть реальные классы сюда
@dataclass
class HistoryMessage:
    role: str  # "user" или "assistant"
    text: str


class LLMClient:
    def __init__(
        self,
        model: str = "gpt-4.1-mini",
        temperature: float = 0.7,
    ) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY не задан. "
                "Установи переменную окружения OPENAI_API_KEY перед запуском бота."
            )

        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.temperature = temperature

    # --------- публичный метод: сгенерировать ответ Алины ---------
    def generate_reply(self, state: Any, new_message: str) -> str:
        """
        state: объект ContactState (username, memory_summary, last_messages и т.д.)
        new_message: текст последнего сообщения пользователя.
        """
        username = getattr(state, "username", "user")
        memory_summary: Optional[str] = getattr(state, "memory_summary", None)
        last_messages: List[Any] = getattr(state, "last_messages", [])

        memory_text = memory_summary or "Пока у меня почти нет информации об этом человеке."

        history_text = self._format_history(last_messages)

        user_prompt = f"""
К тебе пишет пользователь @{username}.

Краткий профиль (то, что ты о нём помнишь):
{memory_text}

Ниже — фрагмент недавней переписки (старые сообщения опущены):
{history_text}

Новое сообщение от пользователя:
\"\"\"{new_message}\"\"\"

Ответь от лица Алины:
- естественно, живо, без официоза;
- не пиши огромные простыни, лучше 1–3 предложения;
- можешь задавать уточняющие вопросы;
- не используй смайлики в виде :) :D, лучше обычный текст или эмодзи.
"""

        try:
            response = self.client.responses.create(
                model=self.model,
                temperature=self.temperature,
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            reply = response.output_text
            return reply.strip()
        except Exception as e:
            # чтобы бот не падал, а просто отвечал заглушкой
            print(f"[LLM] Ошибка generate_reply: {e}")
            return "Немного зависла, но уже вернулась 🙂 Можешь повторить или уточнить, о чём речь?"

    # --------- публичный метод: обновить «память» о пользователе ---------
    def update_memory(self, state: Any, new_message: str, reply: str) -> Dict[str, Any]:
        """
        Возвращает словарь:
        {
          "summary": <краткий профиль>,
          "json": <структурированные данные или None>
        }
        """
        username = getattr(state, "username", "user")
        old_summary: Optional[str] = getattr(state, "memory_summary", None)
        last_messages: List[Any] = getattr(state, "last_messages", [])

        history_text = self._format_history(last_messages)

        user_prompt = f"""
Ты ведёшь краткий профиль пользователя @{username}.

Текущее краткое описание (если есть):
{old_summary or 'нет описания'}

История переписки (обрезанная):
{history_text}

Новое сообщение пользователя:
\"\"\"{new_message}\"\"\"

Твой последний ответ:
\"\"\"{reply}\"\"\"

Сделай:
1. Обнови краткое текстовое описание человека. Не более 3–4 предложений.
2. Опиши в описании:
   - как он обычно пишет (тон, стиль),
   - что ему примерно интересно,
   - как с ним лучше общаться (спокойно, шутливо и т.п.).

Ответь строго в JSON-формате:
{{
  "summary": "<краткое описание на русском>",
  "tags": ["список", "кратких", "тегов"]
}}
"""

        try:
            response = self.client.responses.create(
                model=self.model,
                temperature=0.4,
                input=[
                    {"role": "system", "content": "Ты помогаешь поддерживать краткие профили людей."},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )
            raw = response.output_text
            import json

            data = json.loads(raw)
            summary = data.get("summary", "").strip()
            json_data = data
            return {"summary": summary, "json": json_data}
        except Exception as e:
            print(f"[LLM] Ошибка update_memory: {e}")
            # если не получилось — просто возвращаем старое summary без JSON
            return {
                "summary": old_summary or "",
                "json": None,
            }

    # --------- внутренний хелпер: форматирование истории ---------
    def _format_history(self, last_messages: List[Any], limit: int = 20) -> str:
        """
        last_messages: список объектов, у которых есть .direction ('in'/'out') и .text
        """
        chunks: List[str] = []
        for msg in last_messages[-limit:]:
            direction = getattr(msg, "direction", "in")
            text = getattr(msg, "text", "")

            if not text:
                continue

            if direction == "in":
                prefix = "Пользователь:"
            else:
                prefix = "Алина:"

            chunks.append(f"{prefix} {text}")

        if not chunks:
            return "(история почти пустая)"

        return "\n".join(chunks)