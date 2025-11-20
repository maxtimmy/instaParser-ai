# client/selenium_direct.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Dict

from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver

from bs4 import BeautifulSoup

import time

from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from core.models import ContactSnapshot, MessageSnapshot

class InstagramDirectClient:
    def __init__(
        self,
        driver: WebDriver,
        base_url: str = "https://www.instagram.com",
        wait_timeout: int = 20,
    ) -> None:
        self._driver = driver
        self._base_url = base_url.rstrip("/")
        self._wait = WebDriverWait(self._driver, wait_timeout)
        # Кэш последних превью сообщений по username, чтобы не отвечать на старую историю
        self._last_seen_preview_by_username: Dict[str, str] = {}
        self._poll_initialized: bool = False

    def _load_cookies_if_exist(self, path: str = "cookies.json") -> bool:
        import os, json
        if not os.path.exists(path):
            return False
        self._driver.get(f"{self._base_url}/")
        try:
            with open(path, "r", encoding="utf-8") as f:
                cookies = json.load(f)
        except Exception:
            return False
        for cookie in cookies:
            try:
                self._driver.add_cookie(cookie)
            except Exception:
                continue
        return True

    def _save_cookies(self, path: str = "cookies.json"):
        import json
        cookies = self._driver.get_cookies()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
    """
    Отвечает за работу с веб-интерфейсом Instagram Direct через Selenium:
    - открытие Direct,
    - прокрутка списка диалогов,
    - сбор карточек контактов и конвертация в ContactSnapshot.
    """

    # ------------------ Публичный сценарий ------------------ #
    def _scroll_contacts_list(self, max_scrolls: int = 30, pause: float = 1.0) -> None:
        """
        Прокручивает список контактов вниз, чтобы подгрузить все диалоги.
        Останавливается, если новые контакты перестали появляться.
        """
        # 1. Находим любой тред, чтобы от него подняться к контейнеру
        first_thread = self._wait.until(
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    "div[role='button'][tabindex='0']",
                )
            )
        )

        # 2. Пытаемся найти ближайший скроллируемый контейнер через JavaScript,
        #    а не через жёсткий XPath, т.к. разметка Instagram часто меняется.
        container = self._driver.execute_script(
            """
            let el = arguments[0];
            // сначала идём вверх по предкам и ищем настоящий скроллируемый контейнер
            while (el && el.parentElement) {
                el = el.parentElement;
                const style = window.getComputedStyle(el);
                const oy = style.overflowY;
                if ((oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight) {
                    return el;
                }
            }
            // если не нашли, пробуем найти скроллбар в левой колонке по data-thumb="1"
            const thumb = document.querySelector('div[data-thumb="1"]');
            if (thumb && thumb.parentElement) {
                return thumb.parentElement;
            }
            return null;
            """,
            first_thread,
        )

        if container is None:
            # Если не нашли специфический контейнер, откатываемся к простому скроллу body
            print("[WARN] Не удалось найти контейнер списка диалогов, использую body-scroll")
            self._scroll_threads_list(max_scrolls=max_scrolls)
            return

        last_count = 0
        stable_rounds = 0

        for _ in range(max_scrolls):
            # текущее количество карточек
            threads = self._driver.find_elements(
                By.CSS_SELECTOR,
                "div[role='button'][tabindex='0']",
            )
            cur_count = len(threads)

            if cur_count == last_count:
                stable_rounds += 1
                if stable_rounds >= 2:
                    # два раза подряд ничего нового — выходим
                    break
            else:
                stable_rounds = 0
                last_count = cur_count

            # скроллим контейнер вниз
            self._driver.execute_script(
                "arguments[0].scrollTop = arguments[0].scrollHeight;",
                container,
            )
            time.sleep(pause)

    def _scroll_chat_history_up(self, max_scrolls: int = 50, pause: float = 1.0) -> None:
        """
        Улучшенная прокрутка истории чата:
        - мелкие инкременты вверх;
        - определение достижения верха;
        - затем мелкие инкременты вниз;
        - определение достижения низа.
        """
        try:
            any_bubble = self._wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div[role='button'][aria-label*='Double tap to like']")
                )
            )
        except TimeoutException:
            return

        chat_container = self._driver.execute_script(
            """
            let el = arguments[0];
            while (el && el.parentElement) {
                el = el.parentElement;
                const st = window.getComputedStyle(el);
                const oy = st.overflowY;
                if ((oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight) {
                    return el;
                }
            }
            return null;
            """,
            any_bubble,
        )
        if not chat_container:
            print("[WARN] Не найден контейнер истории для скролла")
            return

        pause = 0.8

        # ---------- scrolling UP ----------
        last_height = None
        stable_rounds = 0

        for _ in range(max_scrolls):
            try:
                cur_height = self._driver.execute_script("return arguments[0].scrollTop;", chat_container)
                self._driver.execute_script(
                    "arguments[0].scrollTop = arguments[0].scrollTop - 200;",
                    chat_container,
                )
                time.sleep(pause)
                new_height = self._driver.execute_script("return arguments[0].scrollTop;", chat_container)

                if new_height == cur_height:
                    stable_rounds += 1
                    if stable_rounds >= 2:
                        break
                else:
                    stable_rounds = 0
            except StaleElementReferenceException:
                break

        # ---------- scrolling DOWN ----------
        stable_rounds = 0
        for _ in range(max_scrolls):
            try:
                cur_top = self._driver.execute_script("return arguments[0].scrollTop;", chat_container)
                cur_sh  = self._driver.execute_script("return arguments[0].scrollHeight;", chat_container)
                cur_ch  = self._driver.execute_script("return arguments[0].clientHeight;", chat_container)

                at_bottom_before = (cur_top + cur_ch) >= (cur_sh - 5)

                self._driver.execute_script(
                    "arguments[0].scrollTop = arguments[0].scrollTop + 200;",
                    chat_container,
                )
                time.sleep(pause)

                new_top = self._driver.execute_script("return arguments[0].scrollTop;", chat_container)
                cur_sh2 = self._driver.execute_script("return arguments[0].scrollHeight;", chat_container)
                cur_ch2 = self._driver.execute_script("return arguments[0].clientHeight;", chat_container)

                at_bottom_after = (new_top + cur_ch2) >= (cur_sh2 - 5)

                if at_bottom_before and at_bottom_after:
                    stable_rounds += 1
                    if stable_rounds >= 2:
                        break
                else:
                    stable_rounds = 0

            except StaleElementReferenceException:
                break

    def _detect_sender(self, bubble_el):
        """
        Определяет отправителя сообщения в пузыре.
        Возвращает "self" или "peer".
        """
        try:
            # Ищем h6 среди предков, в них Instagram показывает "Вы отправили"
            h6_nodes = bubble_el.find_elements(By.XPATH, "ancestor::div//h6")
            for h in h6_nodes:
                txt = (h.text or "").strip()
                if txt.startswith("Вы отправили") or txt.startswith("You sent"):
                    return "self"
        except Exception:
            pass
        return "peer"

    def fetch_contacts(self, max_scrolls: int = 25) -> List[ContactSnapshot]:
        """
        Открывает Direct, прокручивает список диалогов и возвращает
        список "снимков" контактов.
        """
        self._open_direct()
        snapshots: List[ContactSnapshot] = []
        seen_usernames = set()
        scraped_at = datetime.now(timezone.utc)

        for _ in range(max_scrolls if max_scrolls > 0 else 1):
            thread_elements = self._collect_thread_elements()

            html_snapshots: list[str] = []
            for el in thread_elements:
                try:
                    outer_html = el.get_attribute("outerHTML")
                except StaleElementReferenceException:
                    continue
                if not outer_html:
                    continue
                html_snapshots.append(outer_html)

            for outer_html in html_snapshots:
                snapshot = self._parse_thread_element(outer_html, scraped_at)
                if snapshot is None:
                    continue
                if snapshot.username in seen_usernames:
                    continue
                seen_usernames.add(snapshot.username)
                snapshots.append(snapshot)

            # scroll slightly down to fetch new contacts
            try:
                any_thread = thread_elements[0]
            except Exception:
                break

            container = self._driver.execute_script(
                """
                let el = arguments[0];
                while (el && el.parentElement) {
                    el = el.parentElement;
                    const style = window.getComputedStyle(el);
                    const oy = style.overflowY;
                    if ((oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight) {
                        return el;
                    }
                }
                const thumb = document.querySelector('div[data-thumb="1"]');
                if (thumb && thumb.parentElement) {
                    return thumb.parentElement;
                }
                return null;
                """,
                any_thread,
            )
            if not container:
                break

            self._driver.execute_script(
                "arguments[0].scrollTop = arguments[0].scrollTop + 300;",
                container,
            )
            time.sleep(1.0)

        return snapshots

    def close(self):
        try:
            self._driver.quit()
        except:
            pass
    def fetch_messages(self, username: str, limit: int = 50) -> list[MessageSnapshot]:
        """
        Кликает по диалогу с указанным username, парсит messages DOM и возвращает список MessageSnapshot.
        """
        return self.fetch_messages_for_contact(username, limit)

    def open_chat_by_username(self, username: str, retries: int = 3, max_scrolls: int = 40) -> None:
        """
        Открывает диалог в Direct по username.

        Логика:
        - сначала пробует найти диалог среди уже прогруженных карточек;
        - если не получилось — находит скроллируемый контейнер списка диалогов,
          скроллит его небольшими шагами вниз и на каждом шаге ищет нужный username;
        - устойчиво к StaleElementReference.
        """
        xpath = f"//span[@title='{username}']/ancestor::div[@role='button']"

        # -------- 1. Быстрая попытка без скролла --------
        for attempt in range(retries):
            try:
                dialog_button = self._wait.until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                self._driver.execute_script("arguments[0].click();", dialog_button)
                time.sleep(2)
                return
            except StaleElementReferenceException:
                if attempt == retries - 1:
                    print(f"[ERROR] StaleElementReference при открытии диалога {username}, попытки исчерпаны")
                    break
                time.sleep(1)
                continue
            except TimeoutException:
                # не нашли без скролла — идём к плану B
                break

        # -------- 2. Поиск с прокруткой списка диалогов --------
        # Находим любой тред, чтобы от него подняться к контейнеру
        threads = self._collect_thread_elements()
        if not threads:
            print(f"[WARN] Не удалось найти ни одной карточки диалога перед поиском {username}")
            return

        # Пытаемся найти скроллируемый контейнер списка диалогов
        try:
            container = self._driver.execute_script(
                """
                let el = arguments[0];
                while (el && el.parentElement) {
                    el = el.parentElement;
                    const style = window.getComputedStyle(el);
                    const oy = style.overflowY;
                    if ((oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight) {
                        return el;
                    }
                }
                const thumb = document.querySelector('div[data-thumb="1"]');
                if (thumb && thumb.parentElement) {
                    return thumb.parentElement;
                }
                return null;
                """,
                threads[0],
            )
        except Exception:
            container = None

        if not container:
            print(f"[WARN] Не удалось найти контейнер списка диалогов для {username}")
            return

        # Стартуем всегда с самого верха списка, чтобы никого не пропустить
        try:
            self._driver.execute_script("arguments[0].scrollTop = 0;", container)
            time.sleep(0.5)
        except StaleElementReferenceException:
            print(f"[WARN] Контейнер списка диалогов устарел перед поиском {username}")
            return

        # Маленький шаг скролла, чтобы ничего не перескакивать
        scroll_step = 260

        for _ in range(max_scrolls):
            try:
                # Пробуем найти нужную карточку на текущем экране
                try:
                    dialog_button = self._driver.find_element(By.XPATH, xpath)
                    # Нашли — кликаем и выходим
                    self._driver.execute_script("arguments[0].click();", dialog_button)
                    time.sleep(2)
                    return
                except NoSuchElementException:
                    # не видно — скроллим ниже
                    pass

                self._driver.execute_script(
                    "arguments[0].scrollTop = arguments[0].scrollTop + arguments[1];",
                    container,
                    scroll_step,
                )
                time.sleep(0.7)

            except StaleElementReferenceException:
                # Пытаемся восстановить контейнер и продолжить
                print(
                    f"[WARN] StaleElementReference при скролле списка диалогов (поиск {username}), пробую восстановиться"
                )
                try:
                    threads = self._collect_thread_elements()
                    if not threads:
                        print("[WARN] Не удалось заново найти элементы диалогов")
                        break
                    container = self._driver.execute_script(
                        """
                        let el = arguments[0];
                        while (el && el.parentElement) {
                            el = el.parentElement;
                            const style = window.getComputedStyle(el);
                            const oy = style.overflowY;
                            if ((oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight) {
                                return el;
                            }
                        }
                        const thumb = document.querySelector('div[data-thumb="1"]');
                        if (thumb && thumb.parentElement) {
                            return thumb.parentElement;
                        }
                        return null;
                        """,
                        threads[0],
                    )
                    if not container:
                        print("[WARN] Не удалось восстановить контейнер списка диалогов")
                        break
                except Exception:
                    print("[WARN] Исключение при восстановлении контейнера списка диалогов")
                    break

        print(f"[WARN] Не удалось найти диалог с пользователем {username} даже после скролла")

    def send_message(self, text: str) -> None:
        """
        Отправляет сообщение в текущий открытый чат.

        Стараемся быть устойчивыми к изменениям верстки:
        - сначала пробуем textarea с placeholder,
        - затем contenteditable div[role='textbox'].
        """
        # Пробуем textarea
        input_el = None
        try:
            input_el = self._wait.until(
                EC.presence_of_element_located(
                    (
                        By.CSS_SELECTOR,
                        "textarea[placeholder]",
                    )
                )
            )
        except TimeoutException:
            input_el = None

        # Фолбэк: contenteditable div
        if input_el is None:
            try:
                input_el = self._wait.until(
                    EC.presence_of_element_located(
                        (
                            By.XPATH,
                            "//div[@role='textbox' and @contenteditable='true']",
                        )
                    )
                )
            except TimeoutException:
                print("[ERROR] Не найдено поле ввода для отправки сообщения")
                return

        try:
            input_el.click()
            input_el.clear()
        except Exception:
            # на contenteditable clear может не сработать — просто продолжаем
            pass

        input_el.send_keys(text)
        input_el.send_keys(Keys.ENTER)

    def poll_new_messages(self, max_threads: int = 50) -> list[tuple[str, str]]:
        """
        Сканырует список диалогов и возвращает новые входящие сообщения
        в формате [(username, text)].

        Логика:
        - собираем карточки диалогов;
        - парсим username и превью;
        - если у snapshot есть флаг has_unread=True — считаем это новым сообщением;
        - иначе считаем новым изменение превью по сравнению с последним сохранённым.
        """
        thread_elements = self._collect_thread_elements()
        if max_threads > 0:
            thread_elements = thread_elements[:max_threads]

        scraped_at = datetime.now(timezone.utc)
        results: list[tuple[str, str]] = []

        for el in thread_elements:
            try:
                outer_html = el.get_attribute("outerHTML")
            except StaleElementReferenceException:
                continue

            if not outer_html:
                continue

            snapshot = self._parse_thread_element(outer_html, scraped_at)
            if snapshot is None:
                continue

            username = snapshot.username
            preview = snapshot.last_message_preview or ""

            if not username:
                continue

            # отладочный вывод, чтобы видеть, что именно видим в списке диалогов
            print(
                f"[POLL] thread username={username!r}, preview={preview!r}, "
                f"has_unread={getattr(snapshot, 'has_unread', False)!r}"
            )

            # 1) Если есть явный флаг непрочитанности — реагируем сразу
            if getattr(snapshot, "has_unread", False):
                print(f"[POLL] {username!r} has_unread=True → считаем новым сообщением")
                results.append((username, preview))
                self._last_seen_preview_by_username[username] = preview
                continue

            # 2) Иначе работаем через сравнение превью
            last_seen = self._last_seen_preview_by_username.get(username)
            print(f"[POLL] state for {username!r}: last_seen={last_seen!r}, current_preview={preview!r}")
            if last_seen is None:
                # Первый раз видим этот диалог — просто запоминаем состояние
                self._last_seen_preview_by_username[username] = preview
                print(f"[POLL] first time seeing {username!r}, запоминаю preview={preview!r}")
                continue

            if preview and preview != last_seen:
                print(f"[POLL] {username!r} считается новым: preview изменился с {last_seen!r} на {preview!r}")
                self._last_seen_preview_by_username[username] = preview
                results.append((username, preview))

        # помечаем, что хотя бы один раз уже прошлись по списку
        self._poll_initialized = True
        return results


    def remember_last_preview(self, username: str, preview: str) -> None:
        """
        Явно помечает последнее превью для username.
        Используется ботом после отправки собственного сообщения,
        чтобы не реагировать на своё же последнее сообщение.
        """
        self._last_seen_preview_by_username[username] = preview
        self._poll_initialized = True


    def _find_message_bubbles(self):
        """
        Ищет все элементы пузырей сообщений в текущем открытом чате.

        Instagram может использовать разные шаблоны:
        - с aria-label 'Double tap to like' (классический bubble);
        - с локализованным aria-label (на случай других языков);
        - просто div[role='button'] с текстовым div[dir='auto'] внутри.

        Возвращает список WebElement без дублей.
        """
        bubbles = []

        try:
            # 1) Классический шаблон (английский) + возможные локализованные варианты
            css_selectors = [
                "div[role='button'][aria-label*='Double tap to like']",
                "div[role='button'][aria-label*='Дважды коснитесь']",
                "div[role='button'][aria-label*='Дважды нажмите']",
            ]

            for sel in css_selectors:
                try:
                    found = self._driver.find_elements(By.CSS_SELECTOR, sel)
                    if found:
                        bubbles.extend(found)
                except Exception:
                    continue

            # 2) Общий fallback: любой div[role='button'],
            #    внутри которого есть div[@dir='auto' с непустым текстом].
            try:
                generic = self._driver.find_elements(
                    By.XPATH,
                    "//div[@role='button' and .//div[@dir='auto' and normalize-space(text())!='']]",
                )
                bubbles.extend(generic)
            except Exception:
                pass

            # Убираем дубли WebElement по их внутреннему id
            unique = []
            seen_ids = set()
            for el in bubbles:
                try:
                    key = el.id
                except Exception:
                    key = id(el)

                if key in seen_ids:
                    continue
                seen_ids.add(key)
                unique.append(el)

            return unique

        except Exception:
            return []

    def _wait_chat_loaded(self, timeout: int = 20) -> None:
        """
        Ждёт, пока чат после клика по контакту полностью загрузится:
        - либо появляются первые message-bubbles,
        - либо хотя бы main[role='main'] (фолбэк).
        """
        try:
            WebDriverWait(self._driver, timeout).until(
                lambda d: bool(self._find_message_bubbles()) or d.find_elements(By.CSS_SELECTOR, "main[role='main']")
            )
            # даём UI чуть времени стабилизироваться
            time.sleep(1.0)
        except TimeoutException:
            print("[WARN] Не дождались полной загрузки чата (timeout), пробуем парсить то, что есть.")

    def fetch_messages_for_contact(self, username: str, max_scrolls: int = 0) -> list[MessageSnapshot]:
        """
        Открывает чат и собирает все сообщения как список MessageSnapshot.
        """
        self.open_chat_by_username(username)
        self._wait_chat_loaded()
        messages = self._collect_messages_from_chat(contact_username=username, max_scrolls=max_scrolls)
        print(f"[DEBUG] Для {username} собрано сообщений: {len(messages)}")
        return messages

    def _collect_messages_from_chat(
        self,
        contact_username: str,
        max_scrolls: int = 0,
        stop_at_text: Optional[str] = None,
    ) -> list[MessageSnapshot]:
        """
        Сбор сообщений из открытого чата.

        Теперь логика проще и упрямая:
        - всегда скроллим ВВЕРХ (к старым сообщениям);
        - после каждого скролла сразу собираем bubble'ы;
        - выходим в двух случаях:
          1) явно видна "шапка" чата с аватаркой/названием;
          2) очень много раундов без прогресса (ни движения, ни новых bubble'ов).
        """
        # 1. Находим любой bubble, чтобы найти контейнер чата
        try:
            bubbles_initial = self._wait.until(
                lambda d: self._find_message_bubbles()
            )
            any_bubble = bubbles_initial[0]
        except TimeoutException:
            print("[WARN] Не нашли ни одного bubble в чате")
            return []

        chat_container = self._driver.execute_script(
            """
            let el = arguments[0];
            while (el && el.parentElement) {
                el = el.parentElement;
                const st = window.getComputedStyle(el);
                const oy = st.overflowY;
                if ((oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight) {
                    return el;
                }
            }
            return null;
            """,
            any_bubble,
        )
        if not chat_container:
            print("[WARN] Не удалось найти контейнер чата, пробую main[role='main'] как fallback")
            try:
                chat_container = self._driver.find_element(By.CSS_SELECTOR, "main[role='main']")
            except Exception:
                return []

        # 2. Подготовка структур
        snapshots: list[MessageSnapshot] = []
        scraped_at = datetime.now(timezone.utc)
        seen_html: set[str] = set()
        seen_texts: set[str] = set()

        # если max_scrolls == 0 → берём довольно большой лимит раундов
        max_rounds = max_scrolls * 4 if max_scrolls > 0 else 200

        no_progress_rounds = 0
        top_header_rounds = 0

        for _ in range(max_rounds):
            try:
                # 3. Собираем текущие bubble'ы (все известные шаблоны)
                bubbles = self._find_message_bubbles()
                seen_before = len(seen_html)

                for bubble in bubbles:
                    try:
                        bubble_html = bubble.get_attribute("outerHTML")
                    except StaleElementReferenceException:
                        continue
                    if not bubble_html or bubble_html in seen_html:
                        continue
                    seen_html.add(bubble_html)

                    # Текст сообщения
                    try:
                        text_nodes = bubble.find_elements(
                            By.XPATH,
                            ".//*[@dir='auto' and normalize-space(text())!='']",
                        )
                        if not text_nodes:
                            continue
                        text = text_nodes[0].text.strip()
                    except StaleElementReferenceException:
                        continue

                    if not text:
                        continue

                    # Базовая защита от дублей по тексту
                    if text in seen_texts:
                        continue
                    seen_texts.add(text)

                    sender = self._detect_sender(bubble)

                    snapshot = MessageSnapshot(
                        contact_username=contact_username,
                        sender=sender,
                        text=text,
                        timestamp_utc=None,
                        scraped_at_utc=scraped_at,
                    )
                    snapshots.append(snapshot)

                    if stop_at_text and stop_at_text in text:
                        return snapshots

                # 4. Проверяем, не дошли ли до "шапки" переписки
                try:
                    at_top = self._driver.execute_script(
                        "return arguments[0].scrollTop <= 5;",
                        chat_container,
                    )
                except StaleElementReferenceException:
                    at_top = False

                top_header_visible = False
                if at_top:
                    try:
                        top_header_visible = self._driver.execute_script(
                            """
                            const container = arguments[0];
                            // ищем хедер профиля/аккаунта в истории чата
                            const header = container.querySelector(
                                "div[data-scope='messages_table'] img[alt='Аватар пользователя']"
                            );
                            if (!header) return false;
                            const rect = header.getBoundingClientRect();
                            const crect = container.getBoundingClientRect();
                            // считаем, что "в самом верху", если картинка почти прижата к верхней части контейнера
                            return rect.top <= crect.top + 10;
                            """,
                            chat_container,
                        )
                    except Exception:
                        top_header_visible = False

                if at_top and top_header_visible and len(seen_html) == seen_before:
                    top_header_rounds += 1
                else:
                    top_header_rounds = 0

                # если несколько раундов подряд наверху видим "шапку" и новых bubble'ов нет — стоп, это начало чата
                if top_header_rounds >= 3:
                    break

                # 5. Скролл ВВЕРХ маленькими шагами
                try:
                    prev_top = self._driver.execute_script(
                        "return arguments[0].scrollTop;",
                        chat_container,
                    )
                    self._driver.execute_script(
                        "arguments[0].scrollTop = arguments[0].scrollTop - 250;",
                        chat_container,
                    )
                    time.sleep(1.2)
                    new_top = self._driver.execute_script(
                        "return arguments[0].scrollTop;",
                        chat_container,
                    )

                    if new_top == prev_top and len(seen_html) == seen_before:
                        no_progress_rounds += 1
                    else:
                        no_progress_rounds = 0

                    # очень много раундов без движения и без новых сообщений — выходим, чтобы не крутиться бесконечно
                    if no_progress_rounds >= 12:
                        break

                except StaleElementReferenceException:
                    print("[WARN] StaleElementReference при скролле чата, пробую заново найти контейнер")
                    try:
                        bubbles_after = self._wait.until(
                            lambda d: self._find_message_bubbles()
                        )
                        any_bubble = bubbles_after[0]
                        chat_container = self._driver.execute_script(
                            """
                            let el = arguments[0];
                            while (el && el.parentElement) {
                                el = el.parentElement;
                                const st = window.getComputedStyle(el);
                                const oy = st.overflowY;
                                if ((oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight) {
                                    return el;
                                }
                            }
                            return null;
                            """,
                            any_bubble,
                        )
                        if not chat_container:
                            print("[WARN] Не удалось восстановить контейнер чата, выхожу")
                            break
                    except Exception:
                        print("[WARN] Не удалось восстановиться после StaleElementReference")
                        break

            except Exception as e:
                print("[ERROR] Неожиданная ошибка при скролле/сборе сообщений:", repr(e))
                break

        return snapshots
    # ------------------ Вспомогательные методы ------------------ #

    def _open_direct(self) -> None:
        """
        Открывает страницу Direct и ждёт, пока прогрузится список диалогов.
        """
        # 0. Пытаемся загрузить cookies и открыть Direct без логина
        import time
        if self._load_cookies_if_exist():
            self._driver.get(f"{self._base_url}/direct/inbox/")
            time.sleep(3)
            if "/login" not in self._driver.current_url:
                # авторизация успешна
                wait = WebDriverWait(self._driver, 60)
                wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "div[role='button'][tabindex='0'] span[title]")
                    )
                )
                return
            print("[INFO] Cookies существуют, но недействительны — нужен логин.")
        # 1. Фолбэк: просим пользователя залогиниться
        print("[LOGIN] Выполните вход вручную. После логина я сохраню cookies автоматически.")
        self._driver.get(f"{self._base_url}/accounts/login/")
        time.sleep(5)
        WebDriverWait(self._driver, 300).until(
            lambda d: "/direct" in d.current_url or "/inbox" in d.current_url
        )
        time.sleep(3)
        # 2. Сохраняем cookies после успешного входа
        self._save_cookies()

    def _scroll_threads_list(self, max_scrolls: int = 25) -> None:
        """
        Прокручивает список диалогов вниз, чтобы подгрузить максимум контактов.
        Простой вариант: шлём END в <body>.
        """
        body = self._driver.find_element(By.TAG_NAME, "body")

        last_height = None
        same_height_times = 0

        for _ in range(max_scrolls):
            body.send_keys(Keys.END)

            # даём странице чуть времени подгрузить новые элементы
            self._driver.implicitly_wait(1)

            # Проверяем, меняется ли высота документа — если нет, значит докрутили.
            new_height = self._driver.execute_script(
                "return document.body.scrollHeight"
            )
            if last_height is not None and new_height == last_height:
                same_height_times += 1
                if same_height_times >= 3:
                    break
            else:
                same_height_times = 0

            last_height = new_height

    def _collect_thread_elements(self):
        """
        Собирает сырые элементы карточек диалогов.

        Берём общий селектор:
        - div[role='button'][tabindex='0'] — это кликабельные карточки,
        - фильтрацию по span[title] делаем уже при парсинге.
        """
        elements = self._driver.find_elements(
            By.CSS_SELECTOR,
            "div[role='button'][tabindex='0']",
        )
        print(f"[DEBUG] Найдено сырых элементов диалогов: {len(elements)}")
        return elements

    def _parse_thread_element(
        self,
        outer_html: str,
        scraped_at_utc: datetime,
    ) -> Optional[ContactSnapshot]:
        """
        Извлекает данные из HTML одной карточки диалога и превращает их в ContactSnapshot.
        Стараемся быть устойчивыми к изменению верстки:
        - минимальное требование — наличие username;
        - превью и время считаем опциональными и ищем несколькими способами;
        - используем эвристики и fallback-и.
        """
        try:
            soup = BeautifulSoup(outer_html, "html.parser")

            # 1) Имя / username
            # Сначала пробуем классический вариант span[title]
            name_span = soup.select_one("span[title]")

            # Если не нашли, пробуем:
            # - span с data-testid, связанным с именем
            # - любой span с текстом
            if name_span is None:
                # потенциальные кандидаты
                candidates = []

                for sp in soup.select("span"):
                    txt = (sp.get_text(strip=True) or "").strip()
                    if not txt:
                        continue
                    candidates.append(sp)

                # Берём первый осмысленный span как имя
                if candidates:
                    name_span = candidates[0]

            # если вообще не нашли имя — пропускаем карточку
            if name_span is None:
                return None

            name_title = (name_span.get("title") or "").strip()
            name_text = (name_span.get_text(strip=True) or "").strip()

            # username всегда берём из title, если он есть; иначе из текста
            username = name_title or name_text
            if not username:
                return None

            full_name: Optional[str] = None

            # Пытаемся найти full_name как второй span с текстом,
            # отличным от username.
            all_spans = soup.select("span")
            for sp in all_spans:
                txt = (sp.get_text(strip=True) or "").strip()
                if not txt:
                    continue
                if txt != username:
                    full_name = txt
                    break

            # 2) Превью последнего сообщения — по возможности
            preview_text: Optional[str] = None

            # Сначала пробуем span без title, не совпадающий с username/full_name
            for sp in all_spans:
                if sp is name_span:
                    continue
                if sp.has_attr("title"):
                    continue
                txt = (sp.get_text(strip=True) or "").strip()
                if not txt:
                    continue
                if txt in (username, full_name):
                    continue
                preview_text = txt
                break

            # Fallback: div[dir='auto'] с текстом
            if not preview_text:
                for div in soup.select("div[dir='auto']"):
                    txt = (div.get_text(strip=True) or "").strip()
                    if not txt:
                        continue
                    if txt in (username, full_name):
                        continue
                    preview_text = txt
                    break

            # 3) Время последнего сообщения (опционально)
            last_message_at_utc: Optional[datetime] = None

            # 3) Время последнего сообщения (опционально)
            last_message_at_utc: Optional[datetime] = None

            # Пробуем abbr[aria-label] как в исходной версии
            time_str = None
            abbr = soup.select_one("abbr[aria-label]")
            if abbr is not None:
                time_str = (abbr.get("aria-label") or "").strip()

            # Альтернатива: тег time с datetime
            if not time_str:
                time_tag = soup.select_one("time[datetime]")
                if time_tag is not None:
                    time_str = (time_tag.get("datetime") or "").strip()

            # 4) Признак непрочитанного сообщения (синяя точка и т.п.)
            has_unread = False

            # Кандидаты на индикатор непрочитанности
            unread_candidates = []

            # 4.1. aria-label (EN/RU)
            unread_candidates.extend(soup.select("span[aria-label*='Unread']"))
            unread_candidates.extend(soup.select("span[aria-label*='Не прочитано']"))

            # 4.2. Текстовые индикаторы внутри div/span, как в фрагменте:
            # <div ...>Unread</div>
            for tag in soup.select("div, span"):
                txt = (tag.get_text(strip=True) or "").strip().lower()
                if not txt:
                    continue
                if "unread" in txt or "не прочитано" in txt or "непрочитано" in txt:
                    unread_candidates.append(tag)

            # 4.3. Дополнительная эвристика: div'ы с inline-стилями, где в описании встречается 'dot'/'bullet'
            for div in soup.select("div"):
                style = (div.get("style") or "").lower()
                if "dot" in style or "bullet" in style:
                    unread_candidates.append(div)

            if unread_candidates:
                has_unread = True

            snapshot = ContactSnapshot(
                username=username,
                full_name=full_name,
                profile_url=None,
                is_active=True,
                last_message_preview=preview_text,
                last_message_at_utc=last_message_at_utc,
                scraped_at_utc=scraped_at_utc,
            )

            # сохраняем признак непрочитанности, если он есть в разметке
            snapshot.has_unread = has_unread
            return snapshot
        except Exception as e:
            print("[ERROR] Не удалось распарсить карточку из HTML:", repr(e))
            return None
    def open_direct(self) -> None:
        """
        Публичный метод для открытия Direct.
        Обёртка над _open_direct(), чтобы снаружи не дергать приватный метод.
        """
        self._open_direct()