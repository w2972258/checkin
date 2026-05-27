# -*- coding: utf-8 -*-

# =========================================================
# NodeSeek 自动签到（Cloudflare 增强稳定版）
# 适用于：
#   GitHub Actions
#   Cloudflare Turnstile
#   Selenium + undetected_chromedriver
#
# 核心增强：
#   - 真人鼠标轨迹
#   - hover 停顿
#   - profile 持久化
#   - Cloudflare 深层 checkbox 搜索
#   - ShadowRoot 穿透
#   - iframe 智能识别
#   - 高频轻量 watchdog
#   - 更强 stealth
#
# 建议：
#   GitHub Actions 必须启用 xvfb
# =========================================================

import os
import re
import time
import json
import math
import shutil
import random
import logging
import traceback
import subprocess

from pathlib import Path
from datetime import datetime

import requests
import undetected_chromedriver as uc

from selenium.webdriver.common.by import By

# =========================================================
# 环境变量
# =========================================================

COOKIE = os.environ.get("NS_COOKIE", "").strip()

SIGN_MODE = os.environ.get(
    "NS_SIGN_MODE",
    "chicken"
).strip().lower()

ENABLE_SCREENSHOT = (
    os.environ.get("NS_ENABLE_SCREENSHOT", "true").lower()
    == "true"
)

LOG_LEVEL = os.environ.get(
    "NS_LOG_LEVEL",
    "INFO"
).upper()

# =========================================================
# 通知
# =========================================================

PUSH_PLUS_TOKEN = os.environ.get(
    "PUSH_PLUS_TOKEN",
    ""
).strip()

PUSH_PLUS_USER = os.environ.get(
    "PUSH_PLUS_USER",
    ""
).strip()

TG_BOT_TOKEN = os.environ.get(
    "TG_BOT_TOKEN",
    ""
).strip()

TG_USER_ID = os.environ.get(
    "TG_USER_ID",
    ""
).strip()

# =========================================================
# 路径
# =========================================================

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

BASE_DIR = Path(os.getcwd())

SCREENSHOT_DIR = BASE_DIR / "screenshots"
DRIVER_DIR = BASE_DIR / ".driver"
PROFILE_DIR = BASE_DIR / "chrome_profile"

SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
DRIVER_DIR.mkdir(parents=True, exist_ok=True)
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

# =========================================================
# 快照
# =========================================================

def take_snapshot(driver, name_suffix):

    if not ENABLE_SCREENSHOT:
        return None

    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        filename = f"{ts}_{name_suffix}.png"

        path = SCREENSHOT_DIR / filename

        driver.save_screenshot(str(path))

        logging.info(f"📸 快照保存: {path.name}")

        return str(path)

    except Exception as e:
        logging.warning(f"截图失败: {e}")

        return None

# =========================================================
# 通知
# =========================================================

def send(title, content):

    logging.info(f"发送通知: {title}")

    if PUSH_PLUS_TOKEN:

        try:
            requests.post(
                "https://www.pushplus.plus/send",
                json={
                    "token": PUSH_PLUS_TOKEN,
                    "title": title,
                    "content": content
                },
                timeout=15
            )
        except Exception as e:
            logging.warning(f"PushPlus失败: {e}")

    if TG_BOT_TOKEN and TG_USER_ID:

        try:
            requests.post(
                f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
                data={
                    "chat_id": TG_USER_ID,
                    "text": f"{title}\n\n{content}"
                },
                timeout=15
            )

        except Exception as e:
            logging.warning(f"Telegram失败: {e}")

# =========================================================
# 真人鼠标轨迹
# =========================================================

def human_move(driver, start_x, start_y, end_x, end_y):

    steps = random.randint(25, 45)

    for i in range(steps):

        t = i / steps

        ease = t * t * (3 - 2 * t)

        x = start_x + (end_x - start_x) * ease
        y = start_y + (end_y - start_y) * ease

        x += random.uniform(-1.5, 1.5)
        y += random.uniform(-1.5, 1.5)

        driver.execute_cdp_cmd(
            "Input.dispatchMouseEvent",
            {
                "type": "mouseMoved",
                "x": x,
                "y": y,
            }
        )

        time.sleep(random.uniform(0.008, 0.03))

# =========================================================
# 真人点击
# =========================================================

def human_click(driver, x, y):

    start_x = random.randint(50, 500)
    start_y = random.randint(50, 500)

    human_move(
        driver,
        start_x,
        start_y,
        x,
        y
    )

    # hover 停顿
    time.sleep(random.uniform(0.5, 1.5))

    # 微抖动
    for _ in range(random.randint(2, 5)):

        jitter_x = x + random.uniform(-2, 2)
        jitter_y = y + random.uniform(-2, 2)

        driver.execute_cdp_cmd(
            "Input.dispatchMouseEvent",
            {
                "type": "mouseMoved",
                "x": jitter_x,
                "y": jitter_y,
            }
        )

        time.sleep(random.uniform(0.03, 0.08))

    # 按下
    driver.execute_cdp_cmd(
        "Input.dispatchMouseEvent",
        {
            "type": "mousePressed",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1,
        }
    )

    time.sleep(random.uniform(0.08, 0.18))

    # 松开
    driver.execute_cdp_cmd(
        "Input.dispatchMouseEvent",
        {
            "type": "mouseReleased",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1,
        }
    )

# =========================================================
# 获取 Chrome 信息
# =========================================================

def get_chrome_info():

    candidates = [
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser"
    ]

    for name in candidates:

        path = shutil.which(name)

        if not path:
            continue

        try:

            output = subprocess.check_output(
                [path, "--version"],
                text=True
            )

            match = re.search(r"(\\d+)\\.", output)

            if match:
                return path, int(match.group(1))

        except:
            pass

    return None, None

# =========================================================
# Cloudflare 处理
# =========================================================

def try_solve_cloudflare(driver):

    try:

        iframes = driver.find_elements(By.TAG_NAME, "iframe")

        for idx, iframe in enumerate(iframes):

            try:

                iframe_src = (
                    iframe.get_attribute("src")
                    or ""
                ).lower()

                iframe_id = (
                    iframe.get_attribute("id")
                    or ""
                ).lower()

                if (
                    "cloudflare" not in iframe_src
                    and
                    "challenge" not in iframe_src
                    and
                    "turnstile" not in iframe_src
                    and
                    "cf-challenge" not in iframe_id
                ):
                    continue

                logging.info(
                    f"发现 Cloudflare iframe: {idx}"
                )

                rect = driver.execute_script("""
                    const r = arguments[0].getBoundingClientRect();

                    return {
                        x: r.left,
                        y: r.top,
                        width: r.width,
                        height: r.height
                    };
                """, iframe)

                if not rect:
                    continue

                if rect["width"] < 5:
                    continue

                if rect["height"] < 5:
                    continue

                driver.switch_to.frame(iframe)

                # 等 checkbox render
                time.sleep(random.uniform(1.5, 3.0))

                pos = driver.execute_script("""

function deepSearch(root) {

    const selectors = [
        'input[type="checkbox"]',
        '[role="checkbox"]',
        '.ctp-checkbox-label',
        '.ctp-checkbox',
        '.mark',
        '.check',
        '[class*="checkbox"]',
        '[id*="checkbox"]'
    ];

    for (const s of selectors) {

        const el = root.querySelector(s);

        if (el) {

            const r = el.getBoundingClientRect();

            if (r.width > 5 && r.height > 5) {

                return {
                    x: r.left + r.width / 2,
                    y: r.top + r.height / 2
                };
            }
        }
    }

    const all = root.querySelectorAll("*");

    for (const node of all) {

        if (node.shadowRoot) {

            const found = deepSearch(node.shadowRoot);

            if (found) return found;
        }
    }

    return null;
}

return deepSearch(document);

""")

                token_ready = driver.execute_script("""

const input = document.querySelector(
    '[name*="turnstile-response"], [name*="cf-turnstile-response"]'
);

return input && input.value.length > 20;

""")

                driver.switch_to.default_content()

                if token_ready:

                    logging.info("Cloudflare 已自动通过")

                    return True

                if not pos:
                    continue

                click_x = int(rect["x"] + pos["x"])
                click_y = int(rect["y"] + pos["y"])

                logging.info(
                    f"准备真人点击: {click_x}, {click_y}"
                )

                take_snapshot(driver, "before_cf_click")

                human_click(driver, click_x, click_y)

                logging.info("已执行真人点击")

                time.sleep(random.uniform(5, 8))

                take_snapshot(driver, "after_cf_click")

                return True

            except Exception as e:

                try:
                    driver.switch_to.default_content()
                except:
                    pass

                continue

    except Exception as e:

        logging.warning(f"Cloudflare处理异常: {e}")

    return False

# =========================================================
# 等待元素
# =========================================================

def wait_for_element_safely(
    driver,
    by,
    value,
    timeout=60
):

    logging.info(f"等待元素: {value}")

    start_time = time.time()

    while time.time() - start_time < timeout:

        try:

            elements = driver.find_elements(by, value)

            if elements:

                element = elements[0]

                if element.is_displayed():

                    if (
                        value == ".head-info > div"
                        and
                        element.text.strip() == "Loading"
                    ):
                        pass
                    else:
                        return element

        except:
            pass

        # 尝试处理 Cloudflare
        try_solve_cloudflare(driver)

        time.sleep(0.5)

    raise TimeoutError(f"等待元素超时: {value}")

# =========================================================
# 浏览器初始化
# =========================================================

def setup_browser():

    if not COOKIE:

        logging.error("NS_COOKIE为空")

        return None

    chrome_path, chrome_major = get_chrome_info()

    options = uc.ChromeOptions()

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")

    options.add_argument("--window-size=1920,1080")

    options.add_argument("--disable-blink-features=AutomationControlled")

    options.add_argument("--disable-infobars")

    options.add_argument("--lang=en-US")

    options.add_argument("--start-maximized")

    options.add_argument(
        f"--user-data-dir={PROFILE_DIR}"
    )

    options.add_argument(
        "--user-agent=Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )

    driver_path = None

    src = shutil.which("chromedriver")

    if src:

        try:

            dst = DRIVER_DIR / "chromedriver"

            shutil.copy2(src, dst)

            dst.chmod(0o755)

            driver_path = str(dst)

        except:
            pass

    kwargs = {
        "options": options,
        "use_subprocess": True,
        "no_sandbox": True,
    }

    if chrome_path:
        kwargs["browser_executable_path"] = chrome_path

    if driver_path:
        kwargs["driver_executable_path"] = driver_path

    if chrome_major:
        kwargs["version_main"] = chrome_major

    try:

        driver = uc.Chrome(**kwargs)

    except Exception as e:

        logging.error(f"浏览器启动失败: {e}")

        return None

    # =====================================================
    # stealth 注入
    # =====================================================

    try:

        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """

Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});

Object.defineProperty(navigator, 'platform', {
    get: () => 'Win32'
});

Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en']
});

Object.defineProperty(navigator, 'hardwareConcurrency', {
    get: () => 8
});

Object.defineProperty(navigator, 'deviceMemory', {
    get: () => 8
});

window.chrome = {
    runtime: {}
};

const originalQuery = window.navigator.permissions.query;

window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters)
);

"""
            }
        )

    except:
        pass

    # =====================================================
    # 打开首页
    # =====================================================

    logging.info("打开 NodeSeek")

    driver.get("https://www.nodeseek.com")

    time.sleep(random.uniform(2, 4))

    driver.execute_script("""
        window.focus();
        document.body.focus();
    """)

    # =====================================================
    # 注入 Cookie
    # =====================================================

    success_count = 0

    for item in COOKIE.split(";"):

        item = item.strip()

        if "=" not in item:
            continue

        try:

            name, value = item.split("=", 1)

            driver.add_cookie({
                "name": name.strip(),
                "value": value.strip(),
                "domain": ".nodeseek.com",
                "path": "/"
            })

            success_count += 1

        except:
            pass

    logging.info(f"已注入Cookie数量: {success_count}")

    # =====================================================
    # 进入签到页
    # =====================================================

    driver.get("https://www.nodeseek.com/board")

    wait_for_element_safely(
        driver,
        By.CSS_SELECTOR,
        ".head-info > div",
        timeout=90
    )

    return driver

# =========================================================
# 主流程
# =========================================================

if __name__ == "__main__":

    logging.info("========== 开始执行签到 ==========")

    driver = setup_browser()

    if not driver:

        logging.error("浏览器初始化失败")

        exit(1)

    exit_code = 0

    try:

        head_info_div = driver.find_element(
            By.CSS_SELECTOR,
            ".head-info > div"
        )

        buttons = head_info_div.find_elements(
            By.TAG_NAME,
            "button"
        )

        # 已签到
        if not buttons:

            sign_info = head_info_div.text.strip()

            logging.info(f"今日已签到: {sign_info}")

            send(
                "NodeSeek 今日已签到",
                sign_info
            )

            take_snapshot(driver, "already_signed")

        else:

            logging.info("检测到签到按钮")

            if SIGN_MODE == "chicken":

                button = head_info_div.find_element(
                    By.XPATH,
                    ".//button[text()='鸡腿 x 5']"
                )

            else:

                button = head_info_div.find_element(
                    By.XPATH,
                    ".//button[text()='试试手气']"
                )

            driver.execute_script("""
                arguments[0].scrollIntoView({
                    block: 'center'
                });
            """, button)

            time.sleep(random.uniform(1, 2))

            # 真人鼠标移动到按钮附近
            rect = driver.execute_script("""
                const r = arguments[0].getBoundingClientRect();

                return {
                    x: r.left + r.width / 2,
                    y: r.top + r.height / 2
                };
            """, button)

            human_click(
                driver,
                rect["x"],
                rect["y"]
            )

            logging.info("签到按钮已点击")

            time.sleep(random.uniform(5, 8))

            final_info = driver.find_element(
                By.CSS_SELECTOR,
                ".head-info > div"
            ).text.strip()

            logging.info(f"签到结果: {final_info}")

            send(
                "NodeSeek 自动签到成功",
                final_info
            )

            take_snapshot(driver, "sign_success")

    except Exception as e:

        logging.error(f"运行异常: {e}")

        logging.debug(traceback.format_exc())

        take_snapshot(driver, "fatal_error")

        send(
            "NodeSeek 自动签到失败",
            str(e)
        )

        exit_code = 1

    finally:

        logging.info("关闭浏览器")

        try:
            driver.quit()
        except:
            pass

        exit(exit_code)
