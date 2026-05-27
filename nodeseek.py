# -*- coding: utf-8 -*-
# -------------------------------
# NodeSeek GitHub Actions 自动签到脚本 (强力破盾点击版)
# 适配 GitHub Actions / Linux / Headless Chrome
# -------------------------------

import os
import re
import time
import json
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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains


# ========== 环境变量 ==========

COOKIE = os.environ.get("NS_COOKIE", "").strip()

# 签到模式：chicken = 鸡腿 x 5 / lucky = 试试手气
SIGN_MODE = os.environ.get("NS_SIGN_MODE", "chicken").strip().lower()

# 是否启用截图
ENABLE_SCREENSHOT = os.environ.get("NS_ENABLE_SCREENSHOT", "true").lower() == "true"

# 是否启用无头模式，GitHub Actions 建议 true
HEADLESS = os.environ.get("NS_HEADLESS", "true").lower() == "true"

# 日志级别
LOG_LEVEL = os.environ.get("NS_LOG_LEVEL", "INFO").upper()


# ========== 通知环境变量 ==========

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
    """简单通知函数"""
    logging.info(f"通知标题: {title}")
    logging.info(f"通知内容: {content}")

    # PushPlus
    if PUSH_PLUS_TOKEN:
        try:
            url = "https://www.pushplus.plus/send"
            data = {"token": PUSH_PLUS_TOKEN, "title": title, "content": content}
            if PUSH_PLUS_USER: data["topic"] = PUSH_PLUS_USER
            r = requests.post(url, json=data, timeout=15)
            logging.info(f"PushPlus 通知结果: {r.text[:300]}")
        except Exception as e:
            logging.warning(f"PushPlus 通知失败: {e}")

    # Telegram
    if TG_BOT_TOKEN and TG_USER_ID:
        try:
            url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
            data = {"chat_id": TG_USER_ID, "text": f"{title}\n\n{content}"}
            r = requests.post(url, data=data, timeout=15)
            logging.info(f"Telegram 通知结果: {r.text[:300]}")
        except Exception as e:
            logging.warning(f"Telegram 通知失败: {e}")

    # 钉钉机器人
    if DD_BOT_TOKEN and not DD_BOT_SECRET:
        try:
            url = f"https://oapi.dingtalk.com/robot/send?access_token={DD_BOT_TOKEN}"
            data = {"msgtype": "text", "text": {"content": f"{title}\n\n{content}"}}
            r = requests.post(url, json=data, timeout=15)
            logging.info(f"钉钉通知结果: {r.text[:300]}")
        except Exception as e:
            logging.warning(f"钉钉通知失败: {e}")

    # WxPusher
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
    """获取当前环境中的 Chrome 路径和主版本号"""
    candidates = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]
    for name in candidates:
        path = shutil.which(name)
        if not path:
            continue
        try:
            output = subprocess.check_output([path, "--version"], text=True, stderr=subprocess.STDOUT)
            logging.info(f"检测到浏览器: {output.strip()}")
            match = re.search(r"(\d+)\.", output)
            if match:
                return path, int(match.group(1))
        except Exception as e:
            logging.warning(f"读取 Chrome 版本失败: {name}, {e}")
    return None, None

def get_writable_chromedriver():
    """复制系统 chromedriver 到当前项目目录可写路径"""
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


# ========== 核心逻辑：精确定位并点击人机验证框 ==========

def handle_cloudflare_challenge(driver, timeout=25):
    """循环等待直到确认框出现，随后精准模拟点击复选框"""
    logging.info("正在持续扫描是否存在 Cloudflare 人机验证点击框...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        # 寻找 Cloudflare 专属的安全挑战 iframe 元素
        iframes = driver.find_elements(By.XPATH, "//iframe[contains(@src, 'cloudflare') or contains(@title, 'challenge') or contains(@id, 'cf-')]")
        if iframes:
            logging.info("【警告】检测到明显的 Cloudflare Turnstile 验证框！开始执行破盾点击流程...")
            try:
                iframe = iframes[0]
                
                # 1. 滚动让其居中可见
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", iframe)
                time.sleep(random.uniform(1.0, 1.8))
                
                # 2. 方案一：在主父页面框架下，计算偏移量精准击中复选框位置（通常在左侧 X:35, Y:32 附近）
                # 带有随机微调防止固定像素特征被抓
                target_x = random.randint(32, 42)
                target_y = random.randint(28, 36)
                
                actions = ActionChains(driver)
                actions.move_to_element_with_offset(iframe, target_x, target_y)
                actions.click()
                actions.perform()
                logging.info(f"已模拟人类鼠标轨迹对验证框发送物理点击事件 (偏移量 X:{target_x}, Y:{target_y})")
                
                # 3. 方案二：双保险，直接切入 Iframe 内部对确认元素补刀
                try:
                    driver.switch_to.frame(iframe)
                    # Turnstile 内部可交互区域的选择器特征
                    click_targets = driver.find_elements(By.CSS_SELECTOR, "#challenge-stage, .cb-i, input[type='checkbox'], body")
                    if click_targets:
                        inner_actions = ActionChains(driver)
                        inner_actions.move_to_element(click_targets[0]).click().perform()
                        logging.info("Iframe 内部结构点击补救发送成功")
                except Exception as iframe_err:
                    logging.debug(f"Iframe 内部穿透点击未成功（通常由于跨域沙箱隔离，属正常现象）: {iframe_err}")
                finally:
                    # 必须切回主上下文
                    driver.switch_to.default_content()
                
                # 4. 点击完成后延迟观察响应结果
                logging.info("点击完成，等待 Cloudflare 释放网关阻拦...")
                time.sleep(random.uniform(6.0, 8.0))
                return True
                
            except Exception as e:
                logging.warning(f"执行人机复选框点击时出现异常: {e}")
                try:
                    driver.switch_to.default_content()
                except:
                    pass
        
        # 频率不宜过快
        time.sleep(1.5)
        
    logging.info("未发现待挂起的人机验证复选框（可能直接通过或已被动放行）")
    return False


# ========== 浏览器初始化 ==========

def setup_browser():
    """初始化浏览器并注入人机行为对抗"""
    if not COOKIE:
        logging.error("环境变量 NS_COOKIE 为空，请在 GitHub Secrets 中设置 NS_COOKIE")
        return None

    chrome_path, chrome_major = get_chrome_info()
    local_driver = get_writable_chromedriver()

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

    # 随机化稳定的伪装指纹
    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )

    try:
        kwargs = {"options": chrome_options, "use_subprocess": True, "no_sandbox": True}
        if chrome_path: kwargs["browser_executable_path"] = chrome_path
        if local_driver: kwargs["driver_executable_path"] = local_driver
        if chrome_major: kwargs["version_main"] = chrome_major
        driver = uc.Chrome(**kwargs)
    except Exception as e:
        logging.error(f"启动浏览器失败: {e}")
        logging.debug(traceback.format_exc())
        return None

    # 隐藏自动化内核指纹特征
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        })
    except Exception as e:
        logging.warning(f"设置 webdriver 隐藏失败: {e}")

    # 1. 首次敲门访问首页
    logging.info("正在引导浏览器至 NodeSeek 首页...")
    try:
        driver.get("https://www.nodeseek.com")
        WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    except Exception as e:
        logging.warning(f"首页基础容器加载超时: {e}")

    # 2. 检查是否有首屏验证码拦路，有就点击
    handle_cloudflare_challenge(driver, timeout=20)

    # 3. 登录凭证注入（不管过没过盾，都先把 Cookie 灌进去）
    logging.info("正在向当前会话域注入用户 Cookie 身份凭证...")
    success_count = 0
    for item in COOKIE.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        try:
            name, value = item.split("=", 1)
            driver.add_cookie({
                "name": name.strip(),
                "value": value.strip(),
                "domain": ".nodeseek.com",
                "path": "/",
            })
            success_count += 1
        except Exception as e:
            logging.warning(f"添加 Cookie 失败: {item[:30]}..., {e}")
            
    logging.info(f"Cookie 注入完毕，成功应用 {success_count} 项凭证")

    # 4. 刷新页面激活 Cookie
    try:
        logging.info("正在刷新会话页面以全面激活登录态...")
        driver.refresh()
        time.sleep(random.uniform(4.0, 6.0))
    except Exception as e:
        logging.error(f"激活页面刷新失败: {e}")
        take_screenshot(driver, "refresh_failure")
        driver.quit()
        return None

    # 5. 二次验证防反扑：部分时候刷新完后，Cloudflare 会因 Cookie 更新重新要求人类校验点击
    handle_cloudflare_challenge(driver, timeout=15)

    # 6. 验证最终登录状态
    try:
        username_element = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a.Username"))
        )
        logging.info(f"【成功破盾】用户登录态有效，当前账户名: {username_element.text.strip()}")
        return driver
    except Exception:
        logging.error("未检测到预期的账户元素，多半仍被五秒盾封锁或 Cookie 已经失效")
        take_screenshot(driver, "cf_block_or_login_failure")
        driver.quit()
        return None


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
    """检查签到状态"""
    try:
        logging.info("正在访问签到板块详情页")
        driver.get("https://www.nodeseek.com/board")
        WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

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
    """查找并点击具体签到按钮"""
    try:
        logging.info("开始查找签到按钮交互区域")
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
        time.sleep(1)
        button.click()

        logging.info("签到按钮点击成功")
        time.sleep(5)

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
        take_screenshot(driver, "sign_in_failure")
        return False


# ========== 主程序入口 ==========

if __name__ == "__main__":
    logging.info("开始执行 NodeSeek 签到脚本")

    driver = setup_browser()
    if not driver:
        logging.error("浏览器环境初始化或破盾失败，脚本强制退出")
        exit(1)

    exit_code = 0
    try:
        if not click_sign_icon(driver):
            logging.error("点击首页签到图标失败")
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
                    logging.error("执行签到动作失败")
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
