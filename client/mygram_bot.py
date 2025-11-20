from __future__ import annotations

import time
from datetime import datetime, UTC

from client.selenium_direct import InstagramDirectClient
from client.driver_factory import create_driver
from db.contact_repository import ContactRepository
from db.message_repository import MessageRepository
from db.contact_memory_repository import ContactMemoryRepository
from db.contact_state_service import ContactStateService
from core.llm_client import LLMClient

class MyGramBot:
    """
    Основной бот, который:
      - отслеживает новые сообщения в Instagram Direct,
      - получает состояние контакта,
      - генерирует ответ с помощью LLM,
      - отправляет ответ через Selenium,
      - сохраняет память.
    """

    def __init__(self):
        # Selenium
        driver = create_driver(headless=False)
        self.direct = InstagramDirectClient(driver=driver)

        # DB
        contact_repo = ContactRepository()
        message_repo = MessageRepository()
        memory_repo = ContactMemoryRepository()

        # State service
        self.state_service = ContactStateService(
            contact_repo,
            message_repo,
            memory_repo,
            history_limit=20,
        )

        # LLM
        self.llm = LLMClient(model="gpt-4.1-mini")

    def run(self):
        print("[BOT] Запуск бота...")

        # Открываем Direct
        self.direct.open_direct()

        # Основной цикл
        while True:
            new_messages = self.direct.poll_new_messages()
            print(f"[BOT] poll_new_messages вернул {len(new_messages)} новых сообщений")

            for username, preview in new_messages:
                print(f"[BOT] Обрабатываю сообщение: username={username!r}, preview={preview!r}")

                # Получаем реальный текст последнего входящего сообщения из чата
                messages = self.direct.fetch_messages(username, limit=50)
                if messages:
                    incoming_text = messages[-1].text
                else:
                    incoming_text = preview

                print(f"[BOT] Последнее сообщение в чате: {incoming_text!r}")

                # 1. сохраняем входящее сообщение
                self.state_service.save_message(username, "in", incoming_text)

                # 2. загружаем состояние контакта (память + история)
                state = self.state_service.get_contact_state(username)

                # 3. генерируем ответ через LLM
                try:
                    reply = self.llm.generate_reply(state, incoming_text)
                except Exception as e:
                    print(f"[LLM] Ошибка при генерации ответа: {e}")
                    reply = f"Привет, {username}!"

                print(f"[BOT] Ответ: {reply}")
                # 4. отправляем сообщение
                self.direct.open_chat_by_username(username)
                self.direct.send_message(reply)

                # 5. логируем исходящее сообщение
                self.state_service.save_message(username, "out", reply)
                # 6. обновляем память контакта
                try:
                    new_memory = self.llm.update_memory(state, incoming_text, reply)
                    if new_memory and new_memory.get("summary") is not None:
                        self.state_service.update_contact_memory(
                            username,
                            new_memory["summary"],
                            new_memory.get("json"),
                        )
                except Exception as e:
                    print(f"[LLM] Ошибка при обновлении памяти: {e}")

            time.sleep(2)


if __name__ == "__main__":
    bot = MyGramBot()
    bot.run()
