# -*- coding: utf-8 -*-
# -------------------------------
# NodeSeek 自动签到脚本 (全链路逐帧快照·高维日志分析版)
# 专门解决 GitHub Actions 环境下破盾失败问题
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


# ========== 增强版全局快照捕获器 ==========

def take_snapshot(driver, name_suffix):
    """
    流水线级快照落盘函数：自动附加精确到毫秒的时间戳，防止覆盖
    """
    if not ENABLE_SCREENSHOT: return None
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        filename = f"step_{ts}_{name_suffix}.png"
        path = SCREENSHOT_DIR / filename
        driver.save_screenshot(str(path))
        logging.info(f"📸 [快照已安全落地] -> {path.name}")
        return str(path)
    except Exception as e:
        logging.warning(f"⚠️ 快照落地失败 ({name_suffix}): {e}")
        return None

def send(title="NodeSeek 签到通知", content=""):
    logging.info(f"发送通知 -> {title}")
    if PUSH_PLUS_TOKEN:
        try: requests.post("https://www.pushplus.plus/send", json={"token": PUSH_PLUS_TOKEN, "title": title, "content": content}, timeout=10)
        except Exception as e: logging.warning(f"PushPlus 失败: {e}")
    if TG_BOT_TOKEN and TG_USER_ID:
        try: requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage", data={"chat_id": TG_USER_ID, "text": f"{title}\n\n{content}"}, timeout=10)
        except Exception as e: logging.warning(f"Telegram 失败: {e}")


# ========== 【逐帧监控看门狗】动态破盾分析器 ==========

def wait_for_element_safely(driver, by, value, timeout=50, step_name="未知步骤"):
    """
    看门狗：全时段扫描正常元素与潜在的5秒盾。
    加入全方位的日志打印与点击前后多阶段截图。
    """
    logging.info(f"🔍 [监控启动] 正在等待业务元素 [{value}] (当前阶段: {step_name})")
    start_time = time.time()
    shot_counter = 0
    
    while time.time() - start_time < timeout:
        # 1. 检测目标正常业务元素是否已经产生
        try:
            elements = driver.find_elements(by, value)
            if elements and elements[0].is_displayed():
                if value == ".head-info > div" and elements[0].text.strip() == "Loading":
                    pass
                else:
                    logging.info(f"🎉 [监控反馈] 成功捕获目标业务元素: {value}")
                    return elements[0]
        except:
            pass

        # 2. 深度扫描页面中隐藏或公开的所有 Iframe 框架
        try:
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            if iframes:
                logging.debug(f"  -> 当前页面存在 {len(iframes)} 个 Iframe 容器，开始逐一排查指纹...")
                
            for idx, iframe in enumerate(iframes):
                ifr_id = iframe.get_attribute("id") or "无ID"
                ifr_src = iframe.get_attribute("src") or "无SRC"
                
                # 过滤掉明显不是 Cloudflare 的框架（加速排查）
                if "cloudflare" not in ifr_src and "cloudflare" not in ifr_id and "challenge" not in ifr_src:
                    continue
                
                logging.info(f"🚨 [锁定防御壁垒] 发现疑似5秒盾 Iframe [{idx}]: ID={ifr_id}, SRC={ifr_src[:60]}...")
                
                # 获取该 Iframe 的物理盒模型尺寸及偏移
                iframe_box = driver.execute_script("""
                    var rect = arguments[0].getBoundingClientRect();
                    return {x: rect.left, y: rect.top, width: rect.width, height: rect.height};
                """, iframe)
                
                if not iframe_box or iframe_box['width'] == 0 or iframe_box['height'] == 0:
                    logging.warning(f"  -> Iframe [{idx}] 尺寸异常(不可见)，跳过。宽高: {iframe_box}")
                    continue

                logging.info(f"  -> 框架物理坐标: X={iframe_box['x']}, Y={iframe_box['y']}, W={iframe_box['width']}, H={iframe_box['height']}")
                
                # 穿透进入 Iframe 沙箱
                driver.switch_to.frame(iframe)
                
                # 扫描真正的复选框节点相对坐标
                pos = driver.execute_script("""
                    function findRealCheckbox(root) {
                        if (!root) return null;
                        let selectors = [
                            'input[type="checkbox"]',
                            '.ctp-checkbox-label',
                            '.checkmark',
                            'input[id*="ctp-"]',
                            '#challenge-stage',
                            '[class*="checkbox"]'
                        ];
                        for (let s of selectors) {
                            let el = root.querySelector(s);
                            if (el) {
                                var r = el.getBoundingClientRect();
                                if (r.width > 0 && r.height > 0) {
                                    return { selector: s, x: r.left + r.width / 2, y: r.top + r.height / 2 };
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
                
                # 检测是否已经被放行
                token_ready = driver.execute_script("""
                    const input = document.querySelector('[name*="turnstile-response"], [name*="cf-turnstile-response"]');
                    return input && input.value.length > 20;
                """)
                
                # 无论结果如何，火速重归主域空间，确保大循环上下文绝对安全
                driver.switch_to.default_content()

                if token_ready:
                    logging.info("🛡️  [看门狗提示] 检测到通过口令已填入，盾已失效，等待页面自动重定向...")
                    time.sleep(2)
                    break

                if pos:
                    # 融合两层相对偏差，换算出全屏视口下的绝对像素级坐标
                    click_x = int(iframe_box['x'] + pos['x'])
                    click_y = int(iframe_box['y'] + pos['y'])
                    
                    logging.info(f"🎯 [物理核心锁定] 抓取到目标选择器 [{pos['selector']}] 相对坐标: x={pos['x']}, y={pos['y']}")
                    logging.info(f"💥 [物理核心锁定] 换算主域绝对点击坐标 -> ** X: {click_x}, Y: {click_y} **")
                    
                    # 【核心请求】：点击前的快照
                    take_snapshot(driver, f"01_before_click_stage_{step_name}")
                    
                    # 拟真完整物理鼠标交互轨迹
                    logging.info("🖱️ 正在通过 CDP 协议发射物理点击信号...")
                    driver.execute_cdp_cmd('Input.dispatchMouseEvent', {'type': 'mouseMoved', 'x': click_x, 'y': click_y})
                    time.sleep(0.1)
                    driver.execute_cdp_cmd('Input.dispatchMouseEvent', {'type': 'mousePressed', 'x': click_x, 'y': click_y, 'button': 'left', 'clickCount': 1})
                    time.sleep(0.08)
                    driver.execute_cdp_cmd('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'x': click_x, 'y': click_y, 'button': 'left', 'clickCount': 1})
                    
                    # 【核心请求】：点击完瞬间、0.5秒后、3秒后连续快照，捕获动画残影与变化
                    time.sleep(0.1)
                    take_snapshot(driver, f"02_clicked_immediate_{step_name}")
                    
                    time.sleep(0.5)
                    take_snapshot(driver, f"03_clicked_plus_05s_{step_name}")
                    
                    time.sleep(3.5)
                    take_snapshot(driver, f"04_clicked_plus_4s_{step_name}")
                    
                    logging.info("🚀 这一轮物理撞击与多段连续观测完成，重新评估页面状态...")
                    break
            
            # 定期对无盾状态也留个影，便于观察它是不是卡在别的诡异地方
            shot_counter += 1
            if shot_counter % 6 == 0:
                take_snapshot(driver, f"routine_loop_watching_{step_name}")

        except Exception as e:
            try: driver.switch_to.default_content()
            except: pass
            logging.debug(f"看门狗大循环波动: {e}")

        time.sleep(1.5)

    # 最终宣告失败前，强行留下一张遗照
    take_snapshot(driver, f"fatal_timeout_deadline_{step_name}")
    raise TimeoutError(f"在时限内未能突破5秒盾或未能加载目标业务元素 [{value}]。")


# ========== 自动化浏览器环境初始化 ==========

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

    # 1. 请求首页
    logging.info(">>> [01] 正在加载 NodeSeek 首页...")
    driver.get("https://www.nodeseek.com")
    take_snapshot(driver, "00_homepage_initial_load")
    
    try: wait_for_element_safely(driver, By.TAG_NAME, "body", timeout=20, step_name="冷启动首页首检")
    except: pass

    # 2. 注入 Cookie
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
            logging.warning(f"单项 Cookie 注入挂了: {e}")
    logging.info(f">> 已挂载 {success_count} 项明文凭证")

    # 3. 核心节点：执行刷新
    logging.info(">>> [03] 正在对当前域执行刷新，准备激活登录态...")
    driver.refresh()
    
    # 刷新后的第一瞬间，立刻拍下一张，看它到底有没有立刻弹盾
    take_snapshot(driver, "00_after_refresh_immediate")

    # 让高频看门狗贴身保护，等待用户名加载，同时阻击任何瞬间蹦出来的5秒盾
    try:
        username_element = wait_for_element_safely(driver, By.CSS_SELECTOR, "a.Username", timeout=55, step_name="刷新重载激活审查")
        logging.info(f"🎉 【恭喜，越狱成功】已成功识别登录态！当前用户: {username_element.text.strip()}")
        take_snapshot(driver, "00_login_success_state")
        return driver
    except Exception as e:
        logging.error("❌ 失败: 登录态未能在预期内识别，或高精度破盾遭遇超时阻断。")
        take_snapshot(driver, "fatal_error_login_failed_final")
        driver.quit()
        return None


# ========== 核心签到主业务 ==========

if __name__ == "__main__":
    logging.info("================ 开始执行 NodeSeek 自动签到 ================")
    driver = setup_browser()
    if not driver:
        logging.error("浏览器引擎环境初始化失败，被迫终止流程")
        exit(1)

    exit_code = 0
    try:
        # 首页防弹出导引窗处理
        try:
            sign_icon = driver.find_element(By.XPATH, "//span[@title='签到']")
            sign_icon.click()
            time.sleep(2)
        except: pass

        # 切换至 board 控制台
        logging.info(">>> [04] 正在切入用户控制台签到面板...")
        driver.get("https://www.nodeseek.com/board")
        take_snapshot(driver, "04_board_page_entered")
        
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
            
            take_snapshot(driver, "05_before_click_sign_button")
            button.click()
            logging.info("🎯 签到物理实体按钮已成功触发！")
            time.sleep(6)

            try: final_info = driver.find_element(By.CSS_SELECTOR, ".head-info > div").text.strip()
            except: final_info = "签到动作已发送，但最终回执面板读取超时"

            logging.info(f"🎉 签到最终执行回执: {final_info}")
            send(title="NodeSeek 自动签到成功通知", content=final_info)
            
            final_shot = take_snapshot(driver, "05_sign_success_final_done")
            
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
        take_snapshot(driver, "fatal_error_catch_exception")
        exit_code = 1
    finally:
        logging.info(">>> 业务流转完毕，优雅释放内核虚机空间...")
        try: driver.quit()
        except: pass
        exit(exit_code)
