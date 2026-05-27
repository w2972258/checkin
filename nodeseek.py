# -*- coding: utf-8 -*-
# -------------------------------
# NodeSeek GitHub Actions 自动签到脚本 (全局主动防御·全时段动态破盾版)
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


# ========== 辅助工具函数 ==========

def send(title="NodeSeek 签到通知", content=""):
    logging.info(f"发送通知 -> {title}")
    if PUSH_PLUS_TOKEN:
        try: requests.post("https://www.pushplus.plus/send", json={"token": PUSH_PLUS_TOKEN, "title": title, "content": content}, timeout=10)
        except Exception as e: logging.warning(f"PushPlus 失败: {e}")
    if TG_BOT_TOKEN and TG_USER_ID:
        try: requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", data={"chat_id": TG_USER_ID, "text": f"{title}\n\n{content}"}, timeout=10)
        except Exception as e: logging.warning(f"Telegram 失败: {e}")

def take_screenshot(driver, filename_prefix="screenshot"):
    if not ENABLE_SCREENSHOT: return None
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = SCREENSHOT_DIR / f"{filename_prefix}_{ts}.png"
        driver.save_screenshot(str(path))
        logging.info(f"快照已保存: {path}")
        return str(path)
    except Exception as e:
        logging.warning(f"快照保存失败: {e}")
        return None


# ========== 【核心黑科技】全局全时段动态破盾监控器 ==========

def wait_for_element_safely(driver, by, value, timeout=45, step_name="未知步骤"):
    """
    核心看门狗：在等待任何目标元素出现的过程中，时刻保持对5秒盾的扫描。
    一旦发现5秒盾，立即切入、穿透Shadow DOM、换算坐标并使用CDP秒杀它。
    """
    logging.info(f"  [监控启动] 正在等待元素 [{value}]，同时全时段监控5秒盾... (当前目标: {step_name})")
    start_time = time.time()
    challenge_xpath = "//iframe[contains(@src, 'cloudflare') or contains(@id, 'cf-') or contains(@title, 'challenge')]"
    
    while time.time() - start_time < timeout:
        # 1. 尝试探测目标正常元素是否已经就绪
        try:
            elements = driver.find_elements(by, value)
            if elements and elements[0].is_displayed():
                # 如果是面板数据，避开异步 Loading 文本
                if value == ".head-info > div" and elements[0].text.strip() == "Loading":
                    pass
                else:
                    logging.info(f"  [监控反馈] 🎉 成功捕获目标业务元素: {value}")
                    return elements[0]
        except:
            pass

        # 2. 【时刻检测】轰击可能在任意瞬间蹦出来的五秒盾
        try:
            iframes = driver.find_elements(By.XPATH, challenge_xpath)
            for iframe in iframes:
                # 换算 Iframe 视口绝对偏移
                iframe_box = driver.execute_script("""
                    var rect = arguments[0].getBoundingClientRect();
                    return {x: rect.left, y: rect.top, width: rect.width, height: rect.height};
                """, iframe)
                
                if not iframe_box or iframe_box['width'] == 0 or iframe_box['height'] == 0:
                    continue

                # 强行荡过去，刺穿多层沙箱进程
                driver.switch_to.frame(iframe)
                
                # 深度递归突刺 Shadow DOM
                pos = driver.execute_script("""
                    function findTarget(root) {
                        if (!root) return null;
                        let el = root.querySelector('input[type="checkbox"], .ctp-checkbox-label, .checkmark, #challenge-stage');
                        if (el) return el;
                        let kids = root.querySelectorAll('*');
                        for (let i = 0; i < kids.length; i++) {
                            if (kids[i].shadowRoot) {
                                let found = findTarget(kids[i].shadowRoot);
                                if (found) return found;
                            }
                        }
                        return null;
                    }
                    let target = findTarget(document);
                    if (target) {
                        let rect = target.getBoundingClientRect();
                        return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
                    }
                    return null;
                """)
                
                # 检查此 Iframe 内部是否其实已经拿到放行 Token
                token_ready = driver.execute_script("""
                    const input = document.querySelector('[name*="turnstile-response"]');
                    return input && input.value.length > 20;
                """)
                
                # 无论抓到坐标还是 Token，必须光速切回主域，保证大循环上下文绝对安全
                driver.switch_to.default_content()

                if token_ready:
                    logging.info("  [监控反馈] 🛡️ 检测到五秒盾已自行校验通过。")
                    time.sleep(2)
                    break

                if pos:
                    # 融合主视口绝对坐标
                    click_x = int(iframe_box['x'] + pos['x'])
                    click_y = int(iframe_box['y'] + pos['y'])
                    
                    logging.info(f"  [监控反馈] 🚨 逮到了！刷新/跳转触发了5秒盾！绝对坐标: X:{click_x}, Y:{click_y}。拉取 CDP 物理重击...")
                    take_screenshot(driver, "cf_intercepted_before_click")
                    
                    # 高仿真物理轨迹发射
                    driver.execute_cdp_cmd('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': click_x, 'y': click_y})
                    time.sleep(random.uniform(0.1, 0.2))
                    driver.execute_cdp_cmd('Input.dispatchMouseEvent', {'type': 'mousePressed', 'x': click_x, 'y': click_y, 'button': 'left', 'clickCount': 1})
                    time.sleep(random.uniform(0.05, 0.12))
                    driver.execute_cdp_cmd('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'x': click_x, 'y': click_y, 'button': 'left', 'clickCount': 1})
                    
                    logging.info("  [监控反馈] 🚀 CDP 点击信号已精准注入，挂起等待盾释放放行...")
                    time.sleep(7)
                    break # 震碎当前单次 iframe 浅循环，促使外层大监控流重新洗牌判断页面状态
        except Exception as e:
            try: driver.switch_to.default_content()
            except: pass
            logging.debug(f"看门狗线程内遭遇非致命波动: {e}")

        time.sleep(1.5) # 极高密度的检测频率

    raise TimeoutError(f"在 {timeout} 秒内未能成功加载页面或攻破五秒盾拦截。")


# ========== 浏览器初始化环境准备 ==========

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
        logging.error(f"启动浏览器失败: {e}")
        return None

    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"})
    except: pass

    # 1. 加载首页
    logging.info(">>> [01] 正在加载 NodeSeek 首页...")
    driver.get("https://www.nodeseek.com")
    
    # 首次开门检查：可能直接遭遇冷启动5秒盾
    try: wait_for_element_safely(driver, By.TAG_NAME, "body", timeout=30, step_name="首页开门首检")
    except: pass

    # 2. 灌入 Cookie 凭证
    logging.info(">>> [02] 正在向当前会话域灌入身份凭证...")
    success_count = 0
    for item in COOKIE.split(";"):
        item = item.strip()
        if not item or "=" not in item: continue
        try:
            name, value = item.split("=", 1)
            driver.add_cookie({"name": name.strip(), "value": value.strip(), "domain": ".nodeseek.com", "path": "/"})
            success_count += 1
        except Exception as e:
            logging.warning(f"添加 Cookie 失败: {e}")
    logging.info(f">> 已成功激活 {success_count} 项 Cookie 凭证")

    # 3. 【纠正核心】刷新页面激活登录态
    logging.info(">>> [03] 正在刷新重载会话（重点监控刷新产生的5秒盾）...")
    driver.refresh()

    # 刷新后，盾随时会弹出来！让看门狗在等待“用户名元素”的同时，时刻准备击杀5秒盾！
    try:
        username_element = wait_for_element_safely(driver, By.CSS_SELECTOR, "a.Username", timeout=45, step_name="刷新激活登录态后拦截检测")
        logging.info(f"🎉 【成功越狱】成功识别登录状态！当前账户: {username_element.text.strip()}")
        return driver
    except Exception as e:
        logging.error(f"❌ 失败: 登录态验证失败或5秒盾未能在时限内攻破。")
        take_screenshot(driver, "error_login_failed")
        driver.quit()
        return None


# ========== 签到核心主业务流 ==========

if __name__ == "__main__":
    logging.info("================ 开始执行 NodeSeek 自动签到 ================")
    driver = setup_browser()
    if not driver:
        logging.error("浏览器环境初始化或破盾失败，脚本强制退出")
        exit(1)

    exit_code = 0
    try:
        # 尝试点击首页自带的弹出向导（如有）
        try:
            sign_icon = driver.find_element(By.XPATH, "//span[@title='签到']")
            sign_icon.click()
            time.sleep(2)
        except: pass

        # 进入专门的数据面板
        logging.info(">>> [04] 切换至签到控制面板...")
        driver.get("https://www.nodeseek.com/board")
        
        # 跳转控制面板时也有几率弹盾！继续让看门狗全时段护航
        head_info_div = wait_for_element_safely(driver, By.CSS_SELECTOR, ".head-info > div", timeout=35, step_name="进入签到控制面板")

        buttons = head_info_div.find_elements(By.TAG_NAME, "button")
        if not buttons:
            sign_info = head_info_div.text.strip()
            logging.info(f"✅ 结果提示: 今日已完成签到。当前面板状态: {sign_info}")
            send(title="NodeSeek 签到通知 (无需重复执行)", content=sign_info)
            take_screenshot(driver, "04_sign_status_checked")
        else:
            logging.info(">>> [05] 检测到当前处于【尚未签到】状态，开始寻找动作按钮...")
            if SIGN_MODE == "chicken":
                logging.info(">> 策略指派: 优先稳定获取 鸡腿 x 5")
                button = head_info_div.find_element(By.XPATH, ".//button[text()='鸡腿 x 5']")
            else:
                logging.info(">> 策略指派: 试试手气")
                button = head_info_div.find_element(By.XPATH, ".//button[text()='试试手气']")

            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
            time.sleep(1)
            button.click()
            logging.info("🎯 核心签到按钮已被物理击中！")
            time.sleep(6)

            try: final_info = driver.find_element(By.CSS_SELECTOR, ".head-info > div").text.strip()
            except: final_info = "签到动作已触发，但读取最终面板信息超时"

            logging.info(f"🎉 签到最终执行结果: {final_info}")
            send(title="NodeSeek 自动签到成功通知", content=final_info)
            
            final_shot = take_screenshot(driver, "05_sign_success")
            
            if final_shot and TG_BOT_TOKEN and TG_USER_ID:
                try:
                    subprocess.run([
                        "curl", "-s", "-X", "POST", f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto",
                        "-F", f"chat_id={TG_USER_ID}", "-F", f"photo=@{final_shot}",
                        "-F", "caption=🤖 NodeSeek 影子DOM全时段看门狗任务已完美落幕！"
                    ], stdout=subprocess.DEVNULL)
                except: pass

    except Exception as e:
        logging.error(f"💥 异常阻断: {e}")
        logging.debug(traceback.format_exc())
        take_screenshot(driver, "error_catch")
        exit_code = 1
    finally:
        logging.info(">>> 流转结束，安全注销内核引擎...")
        try: driver.quit()
        except: pass
        exit(exit_code)
