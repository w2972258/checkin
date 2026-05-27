# -*- coding: utf-8 -*-
# -------------------------------
# NodeSeek 自动签到脚本 (直达面板·高频去负载看门狗版)
# 专门解决 GitHub Actions 环境下因截图延迟和多余刷新导致的死盾问题
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


# ========== 环境变量 ==========

COOKIE = os.environ.get("NS_COOKIE", "").strip()
SIGN_MODE = os.environ.get("NS_SIGN_MODE", "chicken").strip().lower()
ENABLE_SCREENSHOT = os.environ.get("NS_ENABLE_SCREENSHOT", "true").lower() == "true"
HEADLESS = os.environ.get("NS_HEADLESS", "true").lower() == "true"
LOG_LEVEL = os.environ.get("NS_LOG_LEVEL", "INFO").upper()

# ========== 通知环境变量 ==========

PUSH_PLUS_TOKEN = os.environ.get("PUSH_PLUS_TOKEN", "").strip()
PUSH_PLUS_USER = os.environ.get("PUSH_PLUS_USER", "").strip()
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()
TG_USER_ID = os.environ.get("TG_USER_ID", "").strip()

# ========== 基础配置与路径 ==========

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(message)s")
BASE_DIR = Path(os.getcwd())
SCREENSHOT_DIR = BASE_DIR / "screenshots"
DRIVER_DIR = BASE_DIR / ".driver"

SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
DRIVER_DIR.mkdir(parents=True, exist_ok=True)


# ========== 核心快照与通知 ==========

def take_snapshot(driver, name_suffix):
    if not ENABLE_SCREENSHOT: return None
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"step_{ts}_{name_suffix}.png"
        path = SCREENSHOT_DIR / filename
        driver.save_screenshot(str(path))
        logging.info(f"📸 [快照落地] -> {path.name}")
        return str(path)
    except Exception as e:
        logging.warning(f"⚠️ 快照失败: {e}")
        return None

def send(title="NodeSeek 签到通知", content=""):
    logging.info(f"发送通知 -> {title}")
    if PUSH_PLUS_TOKEN:
        try: requests.post("https://www.pushplus.plus/send", json={"token": PUSH_PLUS_TOKEN, "title": title, "content": content}, timeout=10)
        except Exception as e: logging.warning(f"PushPlus 失败: {e}")
    if TG_BOT_TOKEN and TG_USER_ID:
        try: requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", data={"chat_id": TG_USER_ID, "text": f"{title}\n\n{content}"}, timeout=10)
        except Exception as e: logging.warning(f"Telegram 失败: {e}")


# ========== 【毫秒级响应看门狗】动态破盾分析器 ==========

def wait_for_element_safely(driver, by, value, timeout=60, step_name="未知步骤"):
    """
    去负载高频看门狗：剥离大循环内的截图操作，将轮询延迟压缩至 0.5 秒。
    一秒巡逻两次，一旦捕捉到 Cloudflare 盾，实施 CDP 强力撞击。
    """
    logging.info(f"🔍 [看门狗启动] 目标元素 [{value}] | 阶段: {step_name}")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        # 1. 正常业务元素畅通性检测
        try:
            elements = driver.find_elements(by, value)
            if elements and elements[0].is_displayed():
                if value == ".head-info > div" and elements[0].text.strip() == "Loading":
                    pass  # 避开异步加载文字
                else:
                    logging.info(f"🎉 [业务放行] 成功捕获目标元素: {value}")
                    return elements[0]
        except:
            pass

        # 2. 毫秒级全框架盲扫（剔除例行截图，轻量化运转）
        try:
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for idx, iframe in enumerate(iframes):
                try:  # 内部沙箱保护，防止其中一个 iframe 报错卡死整个扫描流
                    ifr_id = iframe.get_attribute("id") or ""
                    ifr_src = iframe.get_attribute("src") or ""
                    
                    if "cloudflare" not in ifr_src and "challenge" not in ifr_src and "cloudflare" not in ifr_id:
                        continue
                    
                    logging.info(f"🚨 [发现防线] 捕获 5 秒盾容器 [{idx}]: ID={ifr_id or 'None'}, 尺寸探测中...")
                    
                    iframe_box = driver.execute_script("""
                        var rect = arguments[0].getBoundingClientRect();
                        return {x: rect.left, y: rect.top, width: rect.width, height: rect.height};
                    """, iframe)
                    
                    if not iframe_box or iframe_box['width'] == 0 or iframe_box['height'] == 0:
                        continue

                    # 穿透进入沙箱
                    driver.switch_to.frame(iframe)
                    
                    # 深度寻找复选框核心
                    pos = driver.execute_script("""
                        function findRealCheckbox(root) {
                            if (!root) return null;
                            let selectors = ['input[type="checkbox"]', '.ctp-checkbox-label', '.checkmark', 'input[id*="ctp-"]'];
                            for (let s of selectors) {
                                let el = root.querySelector(s);
                                if (el) {
                                    var r = el.getBoundingClientRect();
                                    if (r.width > 0 && r.height > 0) {
                                        return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
                                    }
                                }
                            }
                            let kids = root.querySelectorAll('*');
                            for (let i = 0; i < kids.length; i++) {
                                if (kids[i].shadowRoot) {
                                    let found = findRealCheckbox(kids[i].shadowRoot);
                                    if (found) return found;
                                }
                            }
                            return null;
                        }
                        return findRealCheckbox(document);
                    """)
                    
                    token_ready = driver.execute_script("""
                        const input = document.querySelector('[name*="turnstile-response"], [name*="cf-turnstile-response"]');
                        return input && input.value.length > 20;
                    """)
                    
                    driver.switch_to.default_content() # 立即撤回主域

                    if token_ready:
                        logging.info("🛡️ [看门狗] 5秒盾已自行校验通过，等待释放...")
                        time.sleep(2)
                        break

                    if pos:
                        click_x = int(iframe_box['x'] + pos['x'])
                        click_y = int(iframe_box['y'] + pos['y'])
                        
                        logging.info(f"🎯 [物理锁定] 绝对坐标火速合算完毕 -> X: {click_x}, Y: {click_y}")
                        take_snapshot(driver, f"before_click_cf_{step_name}")
                        
                        # CDP 拟真物理交互
                        driver.execute_cdp_cmd('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': click_x, 'y': click_y})
                        time.sleep(0.05)
                        driver.execute_cdp_cmd('Input.dispatchMouseEvent', {'type': 'mousePressed', 'x': click_x, 'y': click_y, 'button': 'left', 'clickCount': 1})
                        time.sleep(0.06)
                        driver.execute_cdp_cmd('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'x': click_x, 'y': click_y, 'button': 'left', 'clickCount': 1})
                        
                        logging.info("💥 [物理重击] CDP 信号注入完毕，挂起等待防线消散...")
                        time.sleep(6)
                        take_snapshot(driver, f"after_click_cf_{step_name}")
                        break
                except Exception as inner_e:
                    try: driver.switch_to.default_content()
                    except: pass
                    continue
        except Exception as e:
            pass

        time.sleep(0.5) # 极轻量的高频轮询

    take_snapshot(driver, f"fatal_timeout_{step_name}")
    raise TimeoutError(f"在时限内未能加载业务目标 [{value}] 或未能攻破 5 秒盾。")


# ========== 自动化环境就绪 ==========

def get_chrome_info():
    candidates = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]
    for name in candidates:
        path = shutil.which(name)
        if path:
            try:
                output = subprocess.check_output([path, "--version"], text=True)
                match = re.search(r"(\d+)\.", output)
                if match: return path, int(match.group(1))
            except: pass
    return None, None

def setup_browser():
    if not COOKIE:
        logging.error("❌ 错误: 环境变量 NS_COOKIE 为空")
        return None

    chrome_path, chrome_major = get_chrome_info()
    chrome_options = uc.ChromeOptions()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    if HEADLESS:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

    src = shutil.which("chromedriver")
    local_driver = None
    if src:
        dst = DRIVER_DIR / "chromedriver"
        try:
            shutil.copy2(src, dst)
            dst.chmod(0o755)
            local_driver = str(dst)
        except: pass

    try:
        kwargs = {"options": chrome_options, "use_subprocess": True, "no_sandbox": True}
        if chrome_path: kwargs["browser_executable_path"] = chrome_path
        if local_driver: kwargs["driver_executable_path"] = local_driver
        if chrome_major: kwargs["version_main"] = chrome_major
        driver = uc.Chrome(**kwargs)
    except Exception as e:
        logging.error(f"内核引擎初始化失败: {e}")
        return None

    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"})
    except: pass

    # 1. 敲门加载首页以锚定域名
    logging.info(">>> [01] 载入 NodeSeek 宿主主域空间...")
    driver.get("https://www.nodeseek.com")
    
    # 2. 灌入凭证
    logging.info(">>> [02] 正在注入会话身份凭证...")
    success_count = 0
    for item in COOKIE.split(";"):
        item = item.strip()
        if not item or "=" not in item: continue
        try:
            name, value = item.split("=", 1)
            driver.add_cookie({"name": name.strip(), "value": value.strip(), "domain": ".nodeseek.com", "path": "/"})
            success_count += 1
        except Exception as e: pass
    logging.info(f">> 已挂载 {success_count} 项明文凭证")

    # 3. 【纠正核心】绝不原地刷新首页！直接跨步切入到签到控制台页面
    logging.info(">>> [03] 放弃原地刷新！携凭证直奔签到面板控制台...")
    driver.get("https://www.nodeseek.com/board")
    
    # 在进入面板的这一瞬间，让天下武功唯快不破的高频看门狗全权接管！
    try:
        head_info_div = wait_for_element_safely(driver, By.CSS_SELECTOR, ".head-info > div", timeout=60, step_name="直插控制面板并拦截死盾")
        logging.info("🎉 [大捷] 绕过首页防线，成功切入数据面板层！")
        return driver
    except Exception as e:
        logging.error("❌ 失败: 无法进入控制面板，破盾超时或凭证被云端机房风控拒绝。")
        take_snapshot(driver, "fatal_error_login_failed_final")
        driver.quit()
        return None


# ========== 核心签到主业务 ==========

if __name__ == "__main__":
    logging.info("================ 开始执行 NodeSeek 自动签到 ================")
    driver = setup_browser()
    if not driver:
        logging.error("内核初始化失败，安全退出")
        exit(1)

    exit_code = 0
    try:
        # 获取动作状态
        head_info_div = driver.find_element(By.CSS_SELECTOR, ".head-info > div")
        buttons = head_info_div.find_elements(By.TAG_NAME, "button")
        
        if not buttons:
            sign_info = head_info_div.text.strip()
            logging.info(f"✅ 结果提示: 今日已成功完成过签到。当前状态: {sign_info}")
            send(title="NodeSeek 签到通知 (无需重复执行)", content=sign_info)
            take_snapshot(driver, "04_sign_status_already_done")
        else:
            logging.info(">>> [04] 发现未签到实体按钮，准备执行点击...")
            if SIGN_MODE == "chicken":
                logging.info(">> 策略模式: 获取 鸡腿 x 5")
                button = head_info_div.find_element(By.XPATH, ".//button[text()='鸡腿 x 5']")
            else:
                logging.info(">> 策略模式: 试试手气")
                button = head_info_div.find_element(By.XPATH, ".//button[text()='试试手气']")

            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
            time.sleep(1)
            
            button.click()
            logging.info("🎯 签到按钮已成功触发！")
            time.sleep(6)

            try: final_info = driver.find_element(By.CSS_SELECTOR, ".head-info > div").text.strip()
            except: final_info = "签到动作已发送，但最终面板回执读取超时"

            logging.info(f"🎉 签到最终回执结果: {final_info}")
            send(title="NodeSeek 自动签到成功通知", content=final_info)
            take_snapshot(driver, "05_sign_success_final")

    except Exception as e:
        logging.error(f"💥 异常中断: {e}")
        logging.debug(traceback.format_exc())
        take_snapshot(driver, "fatal_exception_catch")
        exit_code = 1
    finally:
        logging.info(">>> 业务流转完毕，注销内核引擎虚机...")
        try: driver.quit()
        except: pass
        exit(exit_code)
