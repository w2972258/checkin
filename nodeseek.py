# -*- coding: utf-8 -*-

import os
import time
import random
import logging
import traceback

import requests
import undetected_chromedriver as uc

from selenium.webdriver.common.by import By


# =========================
# ENV
# =========================

COOKIE = os.environ.get("NS_COOKIE", "").strip()
SIGN_MODE = os.environ.get("NS_SIGN_MODE", "chicken")

LOG_LEVEL = os.environ.get("NS_LOG_LEVEL", "INFO")

PUSH_PLUS_TOKEN = os.environ.get("PUSH_PLUS_TOKEN", "")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_USER_ID = os.environ.get("TG_USER_ID", "")

ENABLE_SCREENSHOT = os.environ.get("NS_ENABLE_SCREENSHOT", "true") == "true"


# =========================
# LOG
# =========================

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

os.makedirs("screenshots", exist_ok=True)


# =========================
# 通知
# =========================

def send(title, content):
    if PUSH_PLUS_TOKEN:
        try:
            requests.post(
                "https://www.pushplus.plus/send",
                json={
                    "token": PUSH_PLUS_TOKEN,
                    "title": title,
                    "content": content
                },
                timeout=10
            )
        except:
            pass

    if TG_BOT_TOKEN and TG_USER_ID:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
                data={
                    "chat_id": TG_USER_ID,
                    "text": f"{title}\n\n{content}"
                },
                timeout=10
            )
        except:
            pass


# =========================
# 截图
# =========================

def snap(driver, name):
    if not ENABLE_SCREENSHOT:
        return
    try:
        driver.save_screenshot(f"screenshots/{name}.png")
    except:
        pass


# =========================
# 人类点击
# =========================

def human_click(driver, x, y):

    start_x = random.randint(50, 400)
    start_y = random.randint(50, 400)

    steps = random.randint(20, 40)

    for i in range(steps):
        t = i / steps
        ease = t * t * (3 - 2 * t)

        mx = start_x + (x - start_x) * ease + random.uniform(-1, 1)
        my = start_y + (y - start_y) * ease + random.uniform(-1, 1)

        driver.execute_cdp_cmd(
            "Input.dispatchMouseEvent",
            {"type": "mouseMoved", "x": mx, "y": my}
        )

        time.sleep(random.uniform(0.01, 0.03))

    time.sleep(random.uniform(0.4, 1.2))

    driver.execute_cdp_cmd(
        "Input.dispatchMouseEvent",
        {"type": "mousePressed", "x": x, "y": y, "button": "left"}
    )

    time.sleep(random.uniform(0.05, 0.15))

    driver.execute_cdp_cmd(
        "Input.dispatchMouseEvent",
        {"type": "mouseReleased", "x": x, "y": y, "button": "left"}
    )


# =========================
# CF iframe 处理（弱化版）
# =========================

def try_cf(driver):
    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")

        for f in iframes:
            src = (f.get_attribute("src") or "").lower()

            if "cloudflare" not in src and "turnstile" not in src:
                continue

            driver.switch_to.frame(f)
            time.sleep(2)

            pos = driver.execute_script("""
                const el = document.querySelector('input[type="checkbox"], [role="checkbox"]');
                if (!el) return null;

                const r = el.getBoundingClientRect();
                return {x: r.left + r.width/2, y: r.top + r.height/2};
            """)

            driver.switch_to.default_content()

            if pos:
                rect = driver.execute_script("""
                    const r = arguments[0].getBoundingClientRect();
                    return {x: r.left, y: r.top};
                """, f)

                x = rect["x"] + pos["x"]
                y = rect["y"] + pos["y"]

                human_click(driver, x, y)

                time.sleep(5)

                return True

    except:
        pass

    return False


# =========================
# browser
# =========================

def start():

    options = uc.ChromeOptions()

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--lang=en-US")

    driver = uc.Chrome(
        options=options,
        use_subprocess=True,
        version_main=120
    )

    return driver


# =========================
# MAIN
# =========================

def main():

    driver = None

    try:
        driver = start()

        driver.get("https://www.nodeseek.com")
        time.sleep(3)

        # inject cookie
        for c in COOKIE.split(";"):
            if "=" not in c:
                continue
            k, v = c.split("=", 1)
            driver.add_cookie({
                "name": k.strip(),
                "value": v.strip(),
                "domain": ".nodeseek.com",
                "path": "/"
            })

        driver.get("https://www.nodeseek.com/board")
        time.sleep(4)

        try_cf(driver)

        time.sleep(3)

        div = driver.find_element(By.CSS_SELECTOR, ".head-info > div")
        btns = div.find_elements(By.TAG_NAME, "button")

        if not btns:
            send("NodeSeek", "今日已签到")
            return

        if SIGN_MODE == "chicken":
            btn = div.find_element(By.XPATH, ".//button[contains(text(),'鸡腿')]")
        else:
            btn = div.find_element(By.XPATH, ".//button[contains(text(),'试试')]")

        rect = driver.execute_script("""
            const r = arguments[0].getBoundingClientRect();
            return {x: r.left + r.width/2, y: r.top + r.height/2};
        """, btn)

        human_click(driver, rect["x"], rect["y"])

        time.sleep(6)

        result = driver.find_element(By.CSS_SELECTOR, ".head-info > div").text

        send("NodeSeek 成功", result)

        snap(driver, "ok")

    except Exception as e:
        logging.error(e)
        logging.error(traceback.format_exc())
        if driver:
            snap(driver, "error")

    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


if __name__ == "__main__":
    main()
