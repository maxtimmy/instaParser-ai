# client/sync_messages_for_all.py

import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from client.selenium_direct import InstagramDirectClient
from db.contact_repository import ContactRepository
from db.message_repository import MessageRepository


def main():
    print("Запускаю Chrome...")
    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")

    driver = webdriver.Chrome(options=options)
    client = InstagramDirectClient(driver)

    # 🔐 Авто-логин:
    # - если есть валидные cookies → сразу зайдёт в Direct;
    # - если cookies нет/протухли → откроет страницу логина и будет
    #   ждать, пока ты вручную залогинишься и попадёшь в Direct.
    #   Никаких input() в консоли.
    client._open_direct()

    # Репозитории
    contacts_repo = ContactRepository()
    messages_repo = MessageRepository()

    # Загружаем список всех контактов из БД
    contacts = contacts_repo.list_all()
    print(f"Найдено контактов в БД: {len(contacts)}")

    for c in contacts:
        username = c.username
        print("=" * 60)
        print(f"Парсю сообщения с пользователем: {username}")

        try:
            # max_scrolls можешь регулировать, если нужно глубже/мельче
            messages = client.fetch_messages_for_contact(
                username=username,
                max_scrolls=12,
            )
        except Exception as e:
            print(f"[Ошибка] Не удалось получить сообщения {username}: {e}")
            continue

        print(f"[DEBUG] Собрано сообщений: {len(messages)}")

        if messages:
            inserted_count = messages_repo.bulk_insert(messages)
        else:
            inserted_count = 0

        print(f"[OK] Сохранено сообщений: {inserted_count}")

        # небольшая пауза между контактами, чтобы не спамить Instagram
        time.sleep(1)

    print("----- Готово. Все контакты обработаны. -----")
    client.close()


if __name__ == "__main__":
    main()