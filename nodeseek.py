# -*- coding: utf-8 -*-
# -------------------------------
# NodeSeek GitHub Actions 自动签到脚本 (主动穿透 Shadow DOM + CDP 仿真轨迹版)
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
WXPUSHER_APP_TOKEN = os.environ.get("WXPUSHER_APP_TOKEN", "").strip()

# ========== 基础配置与路径 ==========

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(message)s")
BASE_DIR = Path(os.getcwd())
SCREENSHOT_DIR = BASE_DIR / "screenshots"
DRIVER_DIR = BASE_DIR / ".driver"

SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
DRIVER_DIR.mkdir(parents=True, exist_ok=True)


# ========== 辅助通知与截图函数 ==========

def send(title="NodeSeek 签到通知", content=""):
    logging.info(f"发送通知 -> {title}")
    if PUSH_PLUS_TOKEN:
        try:
            requests.post("https://www.pushplus.plus/send", json={"token": PUSH_PLUS_TOKEN, "title": title, "content": content}, timeout=10)
        except Exception as e: logging.warning(f"PushPlus 失败: {e}")
    if TG_BOT_TOKEN and TG_USER_ID:
        try:
            requests.post(f"https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage", data={"chat_id": TG_USER_ID, "text": f"{title}\n\n{content}"}, timeout=10)
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


# ========== 核心：穿透拦截框强力处理器 (主动刺穿 Shadow DOM 版) ==========

def solve_any_interceptor_内核版(driver, step_id, step_name, timeout=45):
    logging.info(f"  >> [{step_id}] 拦截检查: {step_name}...")
    start_time = time.time()
    challenge_xpath = "//iframe[contains(@src, 'cloudflare') or contains(@id, 'cf-') or contains(@title, 'challenge')]"
    has_ever_seen_captcha = False

    while time.time() - start_time < timeout:
        current_captcha_found = False
        
        # 1. 优先判定主页面是否已经生成有效的过盾 Token
        try:
            token_main = driver.execute_script("""
                const input = document.querySelector('[name*="turnstile-response"], [name*="cf-turnstile-response"]');
                return input && input.value.length > 20;
            """)
            if token_main:
                logging.info(f"  >> [{step_id}] ✅ Cloudflare 质询已自动通过 (主页面 Token 已就绪)")
                return True
        except:
            pass

        # 2. 捕捉当前页面上的所有验证码 Iframe 容器
        try:
            iframes = driver.find_elements(By.XPATH, challenge_xpath)
        except:
            iframes = []

        for iframe in iframes:
            try:
                # 核心修正：利用 getBoundingClientRect() 精准获取 Iframe 相对于当前浏览器视口的绝对偏移坐标
                iframe_box = driver.execute_script("""
                    var rect = arguments[0].getBoundingClientRect();
                    return {x: rect.left, y: rect.top, width: rect.width, height: rect.height};
                """, iframe)
                
                if not iframe_box or iframe_box['width'] == 0 or iframe_box['height'] == 0:
                    continue

                # 强行切入 Iframe 隔离域内部
                driver.switch_to.frame(iframe)
                
                # 核心黑科技：通过递归 JS 脚本主动刺穿穿透内部的每一层 Shadow DOM 寻找多选框
                pos = driver.execute_script("""
                    function findCheckboxInShadow(root) {
                        if (!root) return null;
                        // 匹配你提供的三大核心指纹选择器
                        let el = root.querySelector('input[type="checkbox"], #challenge-stage, .ctp-checkbox-label, #success-wrapper, .checkmark');
                        if (el) return el;
                        
                        let allEls = root.querySelectorAll('*');
                        for (let i = 0; i < allEls.length; i++) {
                            if (allEls[i].shadowRoot) {
                                let found = findCheckboxInShadow(allEls[i].shadowRoot);
                                if (found) return found;
                            }
                        }
                        return null;
                    }
                    let cb = findCheckboxInShadow(document);
                    if (cb) {
                        let rect = cb.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
                        }
                    }
                    return null;
                """)
                
                # 顺便检查内部 Token 状态
                token_inner = driver.execute_script("""
                    const input = document.querySelector('[name*="turnstile-response"]');
                    return input && input.value.length > 20;
                """)
                
                # 无论结果如何，必须立刻切回主页面，确保后续大循环上下文不丢失
                driver.switch_to.default_content()

                if token_inner:
                    logging.info(f"  >> [{step_id}] ✅ Cloudflare 质询已自动通过 (Iframe 内 Token 已就绪)")
                    return True

                if pos:
                    current_captcha_found = True
                    has_ever_seen_captcha = True
                    
                    # 两层相对坐标叠加，精准算到全屏像素视口点
                    click_x = int(iframe_box['x'] + pos['x'])
                    click_y = int(iframe_box['y'] + pos['y'])
                    
                    logging.info(f"  >> [{step_id}] 🎯 成功刺穿 Shadow DOM 抓取到复选框视口绝对坐标: X:{click_x}, Y:{click_y}")
                    take_screenshot(driver, f"{step_id}_before_cdp_click")
                    
                    # 仿真拟人化物理交互链：移动 -> 按下 -> 弹起
                    # 1. 移动鼠标到目标中心点
                    driver.execute_cdp_cmd('Input.dispatchMouseEvent', {
                        'type': 'mouseMoved', 'x': click_x, 'y': click_y
                    })
                    time.sleep(random.uniform(0.1, 0.2))
                    
                    # 2. 发射原生鼠标左键按下信号
                    driver.execute_cdp_cmd('Input.dispatchMouseEvent', {
                        'type': 'mousePressed', 'x': click_x, 'y': click_y, 'button': 'left', 'clickCount': 1
                    })
                    time.sleep(random.uniform(0.05, 0.12))
                    
                    # 3. 发射原生鼠标左键释放信号
                    driver.execute_cdp_cmd('Input.dispatchMouseEvent', {
                        'type': 'mouseReleased', 'x': click_x, 'y': click_y, 'button': 'left', 'clickCount': 1
                    })
                    
                    logging.info(f"  >> [{step_id}] 🚀 CDP 物理坐标击打指令已成功送达！等待验证码反应...")
                    time.sleep(6)  # 留出充足时间让盾刷新释放网关
                    break  # 打破当前 iframes 浅循环，回到外层等待重新判别整体状态
                    
            except Exception as e:
                try: driver.switch_to.default_content()
                except: pass
                logging.debug(f"探测 Iframe 周期内遭遇微小异常: {e}")

        # 退出放行判定
        if not current_captcha_found and not has_ever_seen_captcha and (time.time() - start_time > 5):
            logging.info(f"  >> [{step_id}] 确认环境干净，未受阻拦")
            return True

        time.sleep(2)
        
    logging.info(f"  >> [{step_id}] ⚠️ 验证处理超时，尝试继续后续主流程...")
    return False


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
        logging.error("❌ 错误: 环境变量 NS_COOKIE 为空，请在 Secrets 中设置")
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

    # 1. 首次加载首页
    logging.info(">>> [01] 正在加载 NodeSeek 首页...")
    try:
        driver.get("https://www.nodeseek.com")
        WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    except Exception as e:
        logging.warning(f"首页基础页面加载超时: {e}")

    # 2. 首屏破盾拦截
    solve_any_interceptor_内核版(driver, "02", "首页首屏五秒盾破盾拦截")
    take_screenshot(driver, "02_homepage_solved")

    # 3. 注入 Cookie
    logging.info(">>> [03] 正在向当前会话域灌入身份凭证...")
    success_count = 0
    for item in COOKIE.split(";"):
        item = item.strip()
        if not item or "=" not in item: continue
        try:
            name, value = item.split("=", 1)
            driver.add_cookie({"name": name.strip(), "value": value.strip(), "domain": ".nodeseek.com", "path": "/"})
            success_count += 1
        except Exception as e:
            logging.warning(f"添加 Cookie 失败: {item[:20]}..., {e}")
    logging.info(f">> 已成功激活 {success_count} 项 Cookie 凭证")

    # 4. 刷新重载会话
    logging.info(">>> [04] 正在重载会话以激活登录态...")
    try:
        driver.refresh()
        time.sleep(5)
    except Exception as e:
        logging.error(f"激活页面刷新失败: {e}")
        driver.quit()
        return None

    # 5. 二次防反扑过盾
    solve_any_interceptor_内核版(driver, "05", "登录态激活后终检")

    # 6. 验证最终登录状态
    try:
        username_element = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.Username")))
        logging.info(f"🎉 【成功越狱】成功识别登录状态！当前账户: {username_element.text.strip()}")
        return driver
    except Exception:
        logging.error("❌ 失败: 未能检测到登录用户名。可能 Cookie 已过期，或者被五秒盾持续拦截。")
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
        try:
            sign_icon = driver.find_element(By.XPATH, "//span[@title='签到']")
            sign_icon.click()
            logging.info(">> 首页签到向导图标触发成功")
            time.sleep(2)
        except:
            pass

        logging.info(">>> [06] 进入数据面板验证今日签到状态...")
        driver.get("https://www.nodeseek.com/board")
        
        head_info_div = WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".head-info > div")))
        
        for _ in range(10):
            if head_info_div.text.strip() != "Loading": break
            time.sleep(1)

        buttons = head_info_div.find_elements(By.TAG_NAME, "button")
        if not buttons:
            sign_info = head_info_div.text.strip()
            logging.info(f"✅ 结果提示: 今日已完成签到。当前面板状态: {sign_info}")
            send(title="NodeSeek 签到通知 (无需重复执行)", content=sign_info)
            take_screenshot(driver, "06_sign_status_checked")
        else:
            logging.info(">>> [07] 检测到当前处于【尚未签到】状态，开始寻找动作按钮...")
            
            if SIGN_MODE == "chicken":
                logging.info(">> 策略指派: 优先稳定获取 鸡腿 x 5")
                button = head_info_div.find_element(By.XPATH, ".//button[text()='鸡腿 x 5']")
            else:
                logging.info(">> 策略指派: 触发极客精神 试试手气")
                button = head_info_div.find_element(By.XPATH, ".//button[text()='试试手气']")

            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
            time.sleep(1)
            button.click()
            logging.info("🎯 核心签到按钮已被物理击中！")
            time.sleep(6)

            try:
                final_info = driver.find_element(By.CSS_SELECTOR, ".head-info > div").text.strip()
            except:
                final_info = "签到动作已触发，但读取最终面板信息超时"

            logging.info(f"🎉 签到最终执行结果: {final_info}")
            send(title="NodeSeek 自动签到成功通知", content=final_info)
            
            final_shot = take_screenshot(driver, "07_sign_success")
            
            if final_shot and TG_BOT_TOKEN and TG_USER_ID:
                try:
                    subprocess.run([
                        "curl", "-s", "-X", "POST", f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto",
                        "-F", f"chat_id={TG_USER_ID}", "-F", f"photo=@{final_shot}",
                        "-F", "caption=🤖 NodeSeek 影子DOM破盾任务已完美落幕！"
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
