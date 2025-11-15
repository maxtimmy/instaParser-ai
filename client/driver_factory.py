# client/driver_factory.py

from selenium import webdriver
from selenium.webdriver.chrome.options import Options


def create_driver(headless: bool = False):
    """
    Создаёт и конфигурирует Chrome WebDriver.
    :param headless: запуск без окна браузера.
    """

    chrome_options = Options()

    # Чтобы не вылазили лишние штуки
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")

    if headless:
        chrome_options.add_argument("--headless=new")

    driver = webdriver.Chrome(options=chrome_options)
    driver.maximize_window()

    return driver