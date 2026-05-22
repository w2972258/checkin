# -*- coding: utf-8 -*-
# -------------------------------
# NodeSeek GitHub Actions 自动签到脚本
# 适配 GitHub Actions / Linux / Headless Chrome
# -------------------------------

import os
import re
import time
import json
import shutil
import logging
import traceback
import subprocess
from pathlib import Path
from datetime import datetime

import requests
import undetected_chromedriver as uc

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# ========== 环境变量 ==========

COOKIE = os.environ.get("NS_COOKIE", "").strip()

# 签到模式：
# chicken = 鸡腿 x 5
# lucky   = 试试手气
SIGN_MODE = os.environ.get("NS_SIGN_MODE", "chicken").strip().lower()

# 是否启用截图
ENABLE_SCREENSHOT = os.environ.get("NS_ENABLE_SCREENSHOT", "true").lower() == "true"

# 是否启用无头模式，GitHub Actions 建议 true
HEADLESS = os.environ.get("NS_HEADLESS", "true").lower() == "true"

# 日志级别
LOG_LEVEL = os.environ.get("NS_LOG_LEVEL", "INFO").upper()


# ========== 通知环境变量，可选 ==========

PUSH_PLUS_TOKEN = os.environ.get("PUSH_PLUS_TOKEN", "").strip()
PUSH_PLUS_USER = os.environ.get("PUSH_PLUS_USER", "").strip()

DD_BOT_SECRET = os.environ.get("DD_BOT_SECRET", "").strip()
DD_BOT_TOKEN = os.environ.get("DD_BOT_TOKEN", "").strip()

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()
TG_USER_ID = os.environ.get("TG_USER_ID", "").strip()

WXPUSHER_APP_TOKEN = os.environ.get("WXPUSHER_APP_TOKEN", "").strip()


# ========== 日志设置 ==========

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)


# ========== 路径设置 ==========

BASE_DIR = Path(os.getcwd())
SCREENSHOT_DIR = BASE_DIR / "screenshots"
DRIVER_DIR = BASE_DIR / ".driver"

SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
DRIVER_DIR.mkdir(parents=True, exist_ok=True)


# ========== 通知函数 ==========

def send(title="NodeSeek 签到通知", content=""):
    """
    简单通知函数。
    没有配置任何通知变量时，只输出日志，不影响签到。
    """

    logging.info(f"通知标题: {title}")
    logging.info(f"通知内容: {content}")

    # PushPlus
    if PUSH_PLUS_TOKEN:
        try:
            url = "https://www.pushplus.plus/send"
            data = {
                "token": PUSH_PLUS_TOKEN,
                "title": title,
                "content": content,
            }
            if PUSH_PLUS_USER:
                data["topic"] = PUSH_PLUS_USER

            r = requests.post(url, json=data, timeout=15)
            logging.info(f"PushPlus 通知结果: {r.text[:300]}")
        except Exception as e:
            logging.warning(f"PushPlus 通知失败: {e}")

    # Telegram
    if TG_BOT_TOKEN and TG_USER_ID:
        try:
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
            data = {
                "chat_id": TG_USER_ID,
                "text": f"{title}\n\n{content}",
            }
            r = requests.post(url, data=data, timeout=15)
            logging.info(f"Telegram 通知结果: {r.text[:300]}")
        except Exception as e:
            logging.warning(f"Telegram 通知失败: {e}")

    # 钉钉机器人，简单版本，不带签名
    if DD_BOT_TOKEN and not DD_BOT_SECRET:
        try:
            url = f"https://oapi.dingtalk.com/robot/send?access_token={DD_BOT_TOKEN}"
            data = {
                "msgtype": "text",
                "text": {
                    "content": f"{title}\n\n{content}"
                }
            }
            r = requests.post(url, json=data, timeout=15)
            logging.info(f"钉钉通知结果: {r.text[:300]}")
        except Exception as e:
            logging.warning(f"钉钉通知失败: {e}")

    # WxPusher 简单版本
    if WXPUSHER_APP_TOKEN:
        try:
            url = "https://wxpusher.zjiecode.com/api/send/message"
            data = {
                "appToken": WXPUSHER_APP_TOKEN,
                "content": f"{title}\n\n{content}",
                "summary": title,
                "contentType": 1,
            }
            r = requests.post(url, json=data, timeout=15)
            logging.info(f"WxPusher 通知结果: {r.text[:300]}")
        except Exception as e:
            logging.warning(f"WxPusher 通知失败: {e}")


# ========== 截图函数 ==========

def take_screenshot(driver, filename_prefix="screenshot"):
    """统一截图函数，仅在启用截图时执行"""
    if not ENABLE_SCREENSHOT:
        return None

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = SCREENSHOT_DIR / f"{filename_prefix}_{timestamp}.png"
        driver.save_screenshot(str(screenshot_path))
        logging.info(f"截图已保存: {screenshot_path}")
        return str(screenshot_path)
    except Exception as e:
        logging.warning(f"截图保存失败: {e}")
        return None


# ========== Chrome / ChromeDriver 处理 ==========

def get_chrome_info():
    """
    获取当前环境中的 Chrome 路径和主版本号。
    GitHub Actions 通常自带 google-chrome。
    """

    candidates = [
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
    ]

    for name in candidates:
        path = shutil.which(name)
        if not path:
            continue

        try:
            output = subprocess.check_output(
                [path, "--version"],
                text=True,
                stderr=subprocess.STDOUT
            )
            logging.info(f"检测到浏览器: {output.strip()}")

            match = re.search(r"(\d+)\.", output)
            if match:
                return path, int(match.group(1))

        except Exception as e:
            logging.warning(f"读取 Chrome 版本失败: {name}, {e}")

    return None, None


def get_writable_chromedriver():
    """
    复制系统 chromedriver 到当前项目目录。
    原因：
    undetected_chromedriver 会 patch chromedriver。
    GitHub Actions 中 /usr/bin/chromedriver 通常不可写。
    """

    src = shutil.which("chromedriver")

    if not src:
        logging.warning("系统中未找到 chromedriver，尝试让 undetected_chromedriver 自动处理")
        return None

    dst = DRIVER_DIR / "chromedriver"

    try:
        shutil.copy2(src, dst)
        dst.chmod(0o755)
        logging.info(f"ChromeDriver 已复制到可写路径: {dst}")
        return str(dst)
    except Exception as e:
        logging.warning(f"复制 chromedriver 失败: {e}")
        return None


# ========== 浏览器初始化 ==========

def setup_browser():
    """初始化浏览器并设置 Cookie"""

    if not COOKIE:
        logging.error("环境变量 NS_COOKIE 为空，请在 GitHub Secrets 中设置 NS_COOKIE")
        return None

    chrome_path, chrome_major = get_chrome_info()
    local_driver = get_writable_chromedriver()

    logging.info(f"Chrome 路径: {chrome_path}")
    logging.info(f"Chrome 主版本: {chrome_major}")
    logging.info(f"ChromeDriver 可写副本: {local_driver}")

    chrome_options = uc.ChromeOptions()

    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")

    if HEADLESS:
        logging.info("启用 headless 模式")
        chrome_options.add_argument("--headless=new")

    # 不建议伪装成固定 Chrome/138，因为 GitHub runner 的 Chrome 版本会变
    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    try:
        kwargs = {
            "options": chrome_options,
            "use_subprocess": True,
            "no_sandbox": True,
        }

        if chrome_path:
            kwargs["browser_executable_path"] = chrome_path

        if local_driver:
            kwargs["driver_executable_path"] = local_driver

        if chrome_major:
            kwargs["version_main"] = chrome_major

        driver = uc.Chrome(**kwargs)

    except Exception as e:
        logging.error(f"启动浏览器失败: {e}")
        logging.debug(traceback.format_exc())
        return None

    # 隐藏 webdriver 特征
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
            Object.defineProperty(navigator, 'webdriver', {
              get: () => undefined
            });
            """
        })
    except Exception as e:
        logging.warning(f"设置 webdriver 隐藏失败: {e}")

    # 首次打开网站，为添加 Cookie 做准备
    logging.info("正在访问 NodeSeek 首页")

    try:
        driver.get("https://www.nodeseek.com")
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        logging.info("NodeSeek 首页加载成功")
    except Exception as e:
        logging.error(f"页面加载失败: {e}")
        take_screenshot(driver, "page_load_failure")
        driver.quit()
        return None

    # 添加 Cookie
    logging.info("开始添加 Cookie")

    success_count = 0

    for item in COOKIE.split(";"):
        item = item.strip()

        if not item or "=" not in item:
            continue

        try:
            name, value = item.split("=", 1)
            name = name.strip()
            value = value.strip()

            if not name or not value:
                continue

            driver.add_cookie({
                "name": name,
                "value": value,
                "domain": ".nodeseek.com",
                "path": "/",
            })

            success_count += 1

        except Exception as e:
            logging.warning(f"添加 Cookie 失败: {item[:30]}..., {e}")

    logging.info(f"Cookie 添加完成，成功添加 {success_count} 项")

    # 刷新页面，让 Cookie 生效
    try:
        driver.refresh()
        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        logging.info("页面刷新成功")
    except Exception as e:
        logging.error(f"页面刷新失败: {e}")
        take_screenshot(driver, "refresh_failure")
        driver.quit()
        return None

    time.sleep(5)

    # 验证登录
    try:
        username_element = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a.Username"))
        )
        username = username_element.text.strip()
        logging.info(f"登录成功，当前账号: {username}")
    except Exception:
        logging.error("未检测到用户名元素，可能 Cookie 无效、过期，或页面结构变化")
        take_screenshot(driver, "login_failure")
        driver.quit()
        return None

    return driver


# ========== 点击签到图标 ==========

def click_sign_icon(driver):
    """点击首页的签到图标"""

    try:
        sign_icon = WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.XPATH, "//span[@title='签到']"))
        )
        sign_icon.click()
        logging.info("签到图标点击成功")
        return True

    except Exception as e:
        logging.error(f"点击签到图标失败: {e}")
        logging.debug(traceback.format_exc())
        take_screenshot(driver, "sign_icon_click_failure")
        return False


# ========== 检查签到状态 ==========

def check_sign_status(driver):
    """
    检查签到状态。
    逻辑：
    进入 /board 页面；
    等待 .head-info > div 加载完成；
    如果没有签到按钮，说明已经签到；
    如果有按钮，说明尚未签到。
    """

    try:
        logging.info("正在访问签到页面")
        driver.get("https://www.nodeseek.com/board")

        WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        head_info_div = WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".head-info > div"))
        )

        WebDriverWait(driver, 60).until(
            lambda d: d.find_element(By.CSS_SELECTOR, ".head-info > div").text.strip() != "Loading"
        )

        buttons = head_info_div.find_elements(By.TAG_NAME, "button")

        if buttons:
            logging.info("今日尚未签到")
            return False

        sign_info = head_info_div.text.strip()
        logging.info(f"检测到已签到信息: {sign_info}")
        send(title="NodeSeek 签到通知", content=sign_info)
        return True

    except Exception as e:
        logging.error(f"检查签到状态失败: {e}")
        logging.debug(traceback.format_exc())
        take_screenshot(driver, "check_sign_status_failure")
        return False


# ========== 点击签到按钮 ==========

def click_sign_button(driver):
    """查找并点击签到按钮"""

    try:
        logging.info("开始查找签到区域")

        sign_div = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((
                By.XPATH,
                "//div[button[text()='鸡腿 x 5'] and button[text()='试试手气']]"
            ))
        )

        logging.info("找到签到区域")

        if SIGN_MODE == "chicken":
            logging.info("准备点击：鸡腿 x 5")
            button = sign_div.find_element(By.XPATH, ".//button[text()='鸡腿 x 5']")

        elif SIGN_MODE == "lucky":
            logging.info("准备点击：试试手气")
            button = sign_div.find_element(By.XPATH, ".//button[text()='试试手气']")

        else:
            logging.error(f"未知签到模式: {SIGN_MODE}，请设置为 chicken 或 lucky")
            return False

        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
        time.sleep(0.5)
        button.click()

        logging.info("签到按钮点击成功")
        time.sleep(5)

        # 签到后再次读取页面信息
        try:
            head_info_div = WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".head-info > div"))
            )
            sign_info = head_info_div.text.strip()
        except Exception:
            sign_info = "签到成功，但未能读取签到后的页面信息"

        logging.info(f"签到结果: {sign_info}")
        send(title="NodeSeek 签到通知", content=sign_info)

        take_screenshot(driver, "sign_success")
        return True

    except Exception as e:
        logging.error(f"签到过程中出错: {e}")
        logging.debug(traceback.format_exc())

        try:
            logging.debug(f"当前页面 URL: {driver.current_url}")
            logging.debug(f"页面源码片段:\n{driver.page_source[:1000]}")
        except Exception:
            pass

        take_screenshot(driver, "sign_in_failure")
        return False


# ========== 主程序 ==========

if __name__ == "__main__":
    logging.info("开始执行 NodeSeek 签到脚本")

    driver = setup_browser()

    if not driver:
        logging.error("浏览器初始化失败")
        exit(1)

    exit_code = 0

    try:
        if not click_sign_icon(driver):
            logging.error("点击签到图标失败")
            exit_code = 1

        else:
            if check_sign_status(driver):
                logging.info("今日已经签到，无需重复签到")
                exit_code = 0
            else:
                if click_sign_button(driver):
                    logging.info("签到流程完成")
                    exit_code = 0
                else:
                    logging.error("签到失败")
                    exit_code = 1

    except Exception as e:
        logging.error(f"主流程异常: {e}")
        logging.debug(traceback.format_exc())
        take_screenshot(driver, "main_failure")
        exit_code = 1

    finally:
        logging.info("脚本执行完毕，关闭浏览器")
        try:
            driver.quit()
        except Exception:
            pass

    exit(exit_code)
