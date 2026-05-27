# -*- coding: utf-8 -*-
# -------------------------------
# NodeSeek GitHub Actions 自动签到脚本 (全框架扫描·高精度 Shadow DOM 击打版)
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


# ========== 辅助通知与快照函数 ==========

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


# ========== 【高精度看门狗】动态全盲扫破盾器 ==========

def wait_for_element_safely(driver, by, value, timeout=50, step_name="未知步骤"):
    """
    全时段防御看门狗：高频轮询业务元素，一旦发现页面有任何 Iframe 弹盾，
    立即进行高精度 Shadow DOM 探测，计算绝对坐标并实施 CDP 物理重击。
    """
    logging.info(f"  [看门狗] 启动 -> 正在等待 [{value}]，同时密切监视全屏5秒盾... ({step_name})")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        # 1. 检查目标正常业务元素是否已经刷出
        try:
            elements = driver.find_elements(by, value)
            if elements and elements[0].is_displayed():
                if value == ".head-info > div" and elements[0].text.strip() == "Loading":
                    pass  # 避开数据面板的异步加载中字样
                else:
                    logging.info(f"  [看门狗] 🎉 业务通道畅通，成功捕获正常元素: {value}")
                    return elements[0]
        except:
            pass

        # 2. 盲扫页面上的所有 Iframe，提防突发弹盾
        try:
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                # 获取该 Iframe 在主视口中的绝对偏移
                iframe_box = driver.execute_script("""
                    var rect = arguments[0].getBoundingClientRect();
                    return {x: rect.left, y: rect.top, width: rect.width, height: rect.height};
                """, iframe)
                
                if not iframe_box or iframe_box['width'] == 0 or iframe_box['height'] == 0:
                    continue

                # 穿透进入 Iframe 隔离沙箱
                driver.switch_to.frame(iframe)
                
                # 【高精度修正】：规避大容器干扰，只锁定真正的复选框物理核心位置
                pos = driver.execute_script("""
                    function findRealCheckbox(root) {
                        if (!root) return null;
                        // 严格按精准度降序排列的选择器指纹
                        let selectors = [
                            'input[type="checkbox"]',
                            '.ctp-checkbox-label',
                            '.checkmark',
                            'input[id*="ctp-"]',
                            '[class*="checkbox"]'
                        ];
                        for (let s of selectors) {
                            let el = root.querySelector(s);
                            if (el) {
                                var r = el.getBoundingClientRect();
                                if (r.width > 0 && r.height > 0) {
                                    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
                                }
                            }
                        }
                        // 没找到则向深层 Shadow DOM 深度递归突刺
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
                
                # 顺便窥探内部是否已经拿到通过口令
                token_ready = driver.execute_script("""
                    const input = document.querySelector('[name*="turnstile-response"], [name*="cf-turnstile-response"]');
                    return input && input.value.length > 20;
                """)
                
                # 无论结果如何，火速重回主域空间，确保主看门狗大循环不卡死
                driver.switch_to.default_content()

                if token_ready:
                    logging.info("  [看门狗] 🛡️ 发现 Cloudflare Token 已就绪，等待网关自动放行...")
                    time.sleep(2)
                    break

                if pos:
                    # 融合两层相对偏差，换算出全屏视口下的绝对像素级坐标
                    click_x = int(iframe_box['x'] + pos['x'])
                    click_y = int(iframe_box['y'] + pos['y'])
                    
                    logging.info(f"  [看门狗] 🚨 锁定5秒盾复选框物理坐标！X: {click_x}, Y: {click_y}。拉取 CDP 执行强力撞击！")
                    take_screenshot(driver, "cf_target_locked")
                    
                    # 拟真完整物理鼠标交互轨迹
                    driver.execute_cdp_cmd('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': click_x, 'y': click_y})
                    time.sleep(random.uniform(0.1, 0.15))
                    driver.execute_cdp_cmd('Input.dispatchMouseEvent', {'type': 'mousePressed', 'x': click_x, 'y': click_y, 'button': 'left', 'clickCount': 1})
                    time.sleep(random.uniform(0.05, 0.1))
                    driver.execute_cdp_cmd('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'x': click_x, 'y': click_y, 'button': 'left', 'clickCount': 1})
                    
                    logging.info("  [看门狗] 🚀 精准物理点击信号已注入！挂起安全等待盾消散...")
                    time.sleep(6)
                    break
        except Exception as e:
            try: driver.switch_to.default_content()
            except: pass
            logging.debug(f"看门狗扫描周期内出现轻微扰动: {e}")

        time.sleep(1.2)  # 高密度高频扫描

    raise TimeoutError(f"在时限内未能突破5秒盾或未能加载目标业务元素 [{value}]。")


# ========== 自动化浏览器基建准备 ==========

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
        logging.error("❌ 错误: 环境变量 NS_COOKIE 未设置")
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

    # 1. 敲门初次加载首页
    logging.info(">>> [01] 正在请求 NodeSeek 首页...")
    driver.get("https://www.nodeseek.com")
    
    try: wait_for_element_safely(driver, By.TAG_NAME, "body", timeout=25, step_name="首页冷启动防线检测")
    except: pass

    # 2. 注入登录 Cookie
    logging.info(">>> [02] 正在注入会话身份凭证...")
    success_count = 0
    for item in COOKIE.split(";"):
        item = item.strip()
        if not item or "=" not in item: continue
        try:
            name, value = item.split("=", 1)
            driver.add_cookie({"name": name.strip(), "value": value.strip(), "domain": ".nodeseek.com", "path": "/"})
            success_count += 1
        except Exception as e:
            logging.warning(f"注入单项 Cookie 失败: {e}")
    logging.info(f">> 成功挂载 {success_count} 项 Cookie 凭证")

    # 3. 刷新页面激活登录态 (此时Actions环境必被云端拉起全屏托管拦截盾)
    logging.info(">>> [03] 执行页面刷新以使登录凭证生效...")
    driver.refresh()

    # 护航看门狗介入！一边等待“用户名”加载，一边时刻准备击杀刷新时随时弹出的5秒盾
    try:
        username_element = wait_for_element_safely(driver, By.CSS_SELECTOR, "a.Username", timeout=50, step_name="刷新激活登录态终审")
        logging.info(f"🎉 【过盾成功】成功登录账户: {username_element.text.strip()}")
        return driver
    except Exception as e:
        logging.error("❌ 失败: 登录态未能在预期内识别，或高精度破盾遭遇超时阻断。")
        take_screenshot(driver, "error_login_failed")
        driver.quit()
        return None


# ========== 核心签到流 ==========

if __name__ == "__main__":
    logging.info("================ 开始执行 NodeSeek 自动签到 ================")
    driver = setup_browser()
    if not driver:
        logging.error("浏览器引擎环境初始化失败，被迫终止流程")
        exit(1)

    exit_code = 0
    try:
        # 兼容处理首页弹出框
        try:
            sign_icon = driver.find_element(By.XPATH, "//span[@title='签到']")
            sign_icon.click()
            time.sleep(2)
        except: pass

        # 切换至 board 面板
        logging.info(">>> [04] 正在切入用户控制台签到面板...")
        driver.get("https://www.nodeseek.com/board")
        
        # 跳转面板过程中同样可能遇到突发校验盾，看门狗继续贴身护航
        head_info_div = wait_for_element_safely(driver, By.CSS_SELECTOR, ".head-info > div", timeout=35, step_name="进入控制面板安全审计")

        buttons = head_info_div.find_elements(By.TAG_NAME, "button")
        if not buttons:
            sign_info = head_info_div.text.strip()
            logging.info(f"✅ 结果提示: 今日已成功完成过签到。当前状态: {sign_info}")
            send(title="NodeSeek 签到通知 (无需重复执行)", content=sign_info)
            take_screenshot(driver, "04_sign_status_checked")
        else:
            logging.info(">>> [05] 检测到当前处于【尚未签到】交互状态，开始捕获目标动作按钮...")
            if SIGN_MODE == "chicken":
                logging.info(">> 策略模式: 稳定获取 鸡腿 x 5")
                button = head_info_div.find_element(By.XPATH, ".//button[text()='鸡腿 x 5']")
            else:
                logging.info(">> 策略模式: 试试手气")
                button = head_info_div.find_element(By.XPATH, ".//button[text()='试试手气']")

            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
            time.sleep(1)
            button.click()
            logging.info("🎯 签到物理实体按钮已成功触发！")
            time.sleep(6)

            try: final_info = driver.find_element(By.CSS_SELECTOR, ".head-info > div").text.strip()
            except: final_info = "签到动作已发送，但最终回执面板读取超时"

            logging.info(f"🎉 签到最终执行回执: {final_info}")
            send(title="NodeSeek 自动签到成功通知", content=final_info)
            
            final_shot = take_screenshot(driver, "05_sign_success")
            
            if final_shot and TG_BOT_TOKEN and TG_USER_ID:
                try:
                    subprocess.run([
                        "curl", "-s", "-X", "POST", f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto",
                        "-F", f"chat_id={TG_USER_ID}", "-F", f"photo=@{final_shot}",
                        "-F", "caption=🤖 NodeSeek 影子DOM全时段高精看门狗任务已完美落幕！"
                    ], stdout=subprocess.DEVNULL)
                except: pass

    except Exception as e:
        logging.error(f"💥 异常中断: {e}")
        logging.debug(traceback.format_exc())
        take_screenshot(driver, "error_catch")
        exit_code = 1
    finally:
        logging.info(">>> 业务流转完毕，优雅释放内核虚机空间...")
        try: driver.quit()
        except: pass
        exit(exit_code)
