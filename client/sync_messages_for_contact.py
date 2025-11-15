# client/sync_messages_for_all.py

import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from client.selenium_direct import InstagramDirectClient
from db.contact_repository import ContactRepository
from db.message_repository import MessageRepository


def main():
    print("Запускаю Chrome для парсинга сообщений...")
    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")

    driver = webdriver.Chrome(options=options)
    client = InstagramDirectClient(driver)

    contacts_repo = ContactRepository()
    messages_repo = MessageRepository()

    try:
        print("Открываю Instagram Direct (куки / логин)...")
        # здесь либо зайдёт по куки, либо один раз попросит логин и сохранит куки
        client._open_direct()

        # Берём контакты из БД — они уже напарсены предыдущим скриптом
        contacts = contacts_repo.list_all()
        print(f"Найдено контактов в БД: {len(contacts)}")

        for c in contacts:
            username = c.username
            print("=" * 60)
            print(f"Парсю сообщения с пользователем: {username}")

            try:
                # max_scrolls можно подправить, если нужно глубже лезть в историю
                messages = client.fetch_messages_for_contact(
                    username=username,
                    max_scrolls=20,
                )
            except Exception as e:
                print(f"[Ошибка] Не удалось получить сообщения {username}: {e}")
                continue

            print(f"[DEBUG] Собрано сообщений: {len(messages)}")
            if not messages:
                continue

            # сохраняем в БД (предполагаем, что репозиторий сам умеет бороться с дублями)
            inserted_count = messages_repo.bulk_insert(messages)
            print(f"[OK] В БД сохранено сообщений: {inserted_count}")

            # небольшая пауза, чтобы Инста не орала
            time.sleep(0.5)

        print("----- Готово. Все контакты обработаны. -----")

    except KeyboardInterrupt:
        print("\n[INFO] Остановлено пользователем (Ctrl+C)")
    finally:
        client.close()
        print("[INFO] Браузер закрыт")


if __name__ == "__main__":
    main()