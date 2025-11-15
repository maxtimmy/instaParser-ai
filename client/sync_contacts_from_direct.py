# client/sync_contacts_from_direct.py

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from client.selenium_direct import InstagramDirectClient
from db.contact_repository import ContactRepository


def main():
    print("Запускаю Chrome для парсинга контактов...")
    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")

    driver = webdriver.Chrome(options=options)
    client = InstagramDirectClient(driver)

    contacts_repo = ContactRepository()

    try:
        print("Открываю Instagram Direct (куки / логин)...")
        # внутри _open_direct:
        # - сначала пробует куки
        # - если они не валидны или отсутствуют — просит залогиниться и сохраняет новые
        client._open_direct()

        print("Парсю контакты из Direct...")
        snapshots = client.fetch_contacts(max_scrolls=25)
        print(f"Собрано контактов: {len(snapshots)}")

        if not snapshots:
            print("[WARN] Контакты не найдены, ничего не сохраняю.")
            return

        # Сохраняем контакты в БД (название метода подстрой под свой репозиторий)
        saved = contacts_repo.bulk_upsert(snapshots)
        print(f"[OK] В БД обновлено/добавлено контактов: {saved}")

    except KeyboardInterrupt:
        print("\n[INFO] Остановлено пользователем (Ctrl+C)")
    finally:
        client.close()
        print("[INFO] Браузер закрыт")


if __name__ == "__main__":
    main()