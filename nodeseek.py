# -*- coding: utf-8 -*-
# -------------------------------
# NodeSeek 自动签到脚本 (纯 CDP 拟真行为与物理落点高亮版)
# -------------------------------

import os
import re
import time
import math
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
from PIL import Image, ImageDraw  # 用于在快照上绘制虚拟鼠标物理落点


# ========== 环境变量 ==========

COOKIE = os.environ.get("NS_COOKIE", "").strip()
SIGN_MODE = os.environ.get("NS_SIGN_MODE", "chicken").strip().lower()
ENABLE_SCREENSHOT = os.environ.get("NS_ENABLE_SCREENSHOT", "true").lower() == "true"

# 注意：配合 GitHub Actions 的 Xvfb 时，此处将被外部 YAML 的 NS_HEADLESS 覆盖为 "false"
HEADLESS = os.environ.get("NS_HEADLESS", "true").lower() == "true"
LOG_LEVEL = os.environ.get("NS_LOG_LEVEL", "INFO").upper()

# ========== 通知配置 ==========
PUSH_PLUS_TOKEN = os.environ.get("PUSH_PLUS_TOKEN", "").strip()
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()
TG_USER_ID = os.environ.get("TG_USER_ID", "").strip()

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(message)s")
BASE_DIR = Path(os.getcwd())
SCREENSHOT_DIR = BASE_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


# ========== 辅助核心函数 ==========

def get_chrome_major_version():
    """
    动态嗅探系统真实安装的 Chrome 主版本号，用于驱动防撞
    """
    for name in ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]:
        path = shutil.which(name)
        if path:
            try:
                output = subprocess.check_output([path, "--version"], text=True)
                match = re.search(r"(\d+)\.", output)
                if match: 
                    return int(match.group(1))
            except: 
                pass
    return None


def take_snapshot(driver, name_suffix, mouse_pos=None):
    """
    高级全景快照：如果传入 mouse_pos=(x, y)，则在最终导出的图片中强制以红圈和十字准心标出鼠标绝对落点
    """
    if not ENABLE_SCREENSHOT: return
    try:
        ts = datetime.now().strftime("%H%M%S")
        path = SCREENSHOT_DIR / f"step_{ts}_{name_suffix}.png"
        
        # 1. 保存常规 DOM 页面截图
        driver.save_screenshot(str(path))
        
        # 2. 注入仿真红圈鼠标点（用于人工复查验证框落点偏差）
        if mouse_pos:
            x, y = mouse_pos
            img = Image.open(path)
            draw = ImageDraw.Draw(img)
            
            r = 10
            # 绘制红圈与十字线
            draw.ellipse((x - r, y - r, x + r, y + r), outline="red", width=3)
            draw.line((x - r - 8, y, x + r + 8, y), fill="red", width=2)
            draw.line((x, y - r - 8, x, y + r + 8), fill="red", width=2)
            
            img.save(path)
            logging.info(f"📸 [带鼠标物理高亮快照] -> {path.name} (坐标: {x}, {y})")
        else:
            logging.info(f"📸 [快照] -> {path.name}")
    except Exception as e: 
        logging.debug(f"快照生成失败: {e}")


def human_move_cdp(driver, start_x, start_y, end_x, end_y):
    """
    通过纯 CDP (Input.dispatchMouseEvent) 绝对坐标注入真实人类鼠标移动轨迹
    """
    logging.info(f"🖱️ 激活纯 CDP 绝对轨迹协议: ({start_x}, {start_y}) -> ({end_x}, {end_y})")
    steps = random.randint(30, 55)
    
    for i in range(steps):
        t = i / steps
        # 线性前进结合随机生物震颤噪点
        x = start_x + (end_x - start_x) * t + random.uniform(-1.5, 1.5)
        y = start_y + (end_y - start_y) * t + random.uniform(-1.5, 1.5)
        
        driver.execute_cdp_cmd(
            "Input.dispatchMouseEvent",
            {
                "type": "mouseMoved",
                "x": int(x),
                "y": int(y)
            }
        )
        time.sleep(random.uniform(0.008, 0.025))

def wait_for_element_safely(driver, by, value, timeout=60, step_name="未知"):
    logging.info(f"🔍 [看门狗] 搜寻 [{value}] | 阶段: {step_name}")
    start_time = time.time()
    cur_x, cur_y = random.randint(10, 40), random.randint(10, 40)

    while time.time() - start_time < timeout:
        # 通道1：业务层就绪检测
        try:
            elements = driver.find_elements(by, value)
            if elements and elements[0].is_displayed():
                if value == ".head-info > div" and elements[0].text.strip() == "Loading": 
                    pass
                else: 
                    return elements[0]
        except Exception as e:
            pass

        # 通道2：CF 盾穿透与几何盲击检测
        try:
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                try:
                    ifr_id = iframe.get_attribute("id") or ""
                    ifr_src = iframe.get_attribute("src") or ""
                    
                    if "cloudflare" not in ifr_src and "challenge" not in ifr_src and "cloudflare" not in ifr_id:
                        continue
                    
                    # 获取 Iframe 绝对视口边界
                    iframe_box = driver.execute_script("""
                        var rect = arguments[0].getBoundingClientRect();
                        return {x: rect.left, y: rect.top, width: rect.width, height: rect.height};
                    """, iframe)
                    
                    if not iframe_box or iframe_box['width'] == 0 or iframe_box['height'] == 0:
                        continue

                    # 切换上下文寻靶
                    driver.switch_to.frame(iframe)
                    pos = driver.execute_script("""
                        function findBox(root) {
                            if (!root) return null;
                            let selectors = ['input[type="checkbox"]', '.ctp-checkbox-label', '.checkmark', '#challenge-stage', '[id*="challenge"]'];
                            for (let s of selectors) {
                                let el = root.querySelector(s);
                                if (el && el.getBoundingClientRect().width > 0) {
                                    var r = el.getBoundingClientRect();
                                    return { x: r.left + r.width/2, y: r.top + r.height/2 };
                                }
                            }
                            let kids = root.querySelectorAll('*');
                            for (let i=0; i<kids.length; i++) {
                                if (kids[i].shadowRoot) {
                                    let f = findBox(kids[i].shadowRoot);
                                    if (f) return f;
                                }
                            }
                            return null;
                        }
                        return findBox(document);
                    """)
                except Exception as iframe_inner_e:
                    logging.debug(f"Iframe 内部解析异常: {iframe_inner_e}")
                    pos = None
                finally:
                    # 核心修复：确保无论如何必须回归主文档域，打破锁死僵局
                    try: driver.switch_to.default_content()
                    except: pass

                # 判定坐标：精准锁定或几何盲击
                if pos:
                    click_x = int(iframe_box['x'] + pos['x'])
                    click_y = int(iframe_box['y'] + pos['y'])
                    logging.info(f"🚨 [精准锁定] 找到验证框原子节点 -> X: {click_x}, Y: {click_y}")
                else:
                    # 兜底：DOM 节点被隐藏混淆，执行几何盲击（Turnstile标准尺寸 300x65，复选框在中左侧）
                    click_x = int(iframe_box['x'] + 35) 
                    click_y = int(iframe_box['y'] + (iframe_box['height'] / 2))
                    logging.warning(f"⚠️ [几何盲击] 虽未在 DOM 中定位到节点，但捕获到 CF Iframe 边界，对准标准复选框中心点发起盲击 -> X: {click_x}, Y: {click_y}")

                # 执行点击流行为
                human_move_cdp(driver, cur_x, cur_y, click_x, click_y)
                time.sleep(random.uniform(0.2, 0.4))
                
                take_snapshot(driver, "before_cdp_click", mouse_pos=(click_x, click_y))
                
                driver.execute_cdp_cmd('Input.dispatchMouseEvent', {'type': 'mousePressed', 'x': click_x, 'y': click_y, 'button': 'left', 'clickCount': 1})
                time.sleep(random.uniform(0.07, 0.12))
                driver.execute_cdp_cmd('Input.dispatchMouseEvent', {'type': 'mouseReleased', 'x': click_x, 'y': click_y, 'button': 'left', 'clickCount': 1})
                
                logging.info("💥 CDP 脉冲发射完毕，死等 6 秒观察防线反应...")
                time.sleep(6)
                
                take_snapshot(driver, "after_cdp_click", mouse_pos=(click_x, click_y))
                
                cur_x, cur_y = click_x, click_y
                break
        except Exception as e:
            logging.debug(f"外层通道异常: {e}")
            
        time.sleep(0.5)

    take_snapshot(driver, "fatal_timeout")
    raise TimeoutError("时限内未通过验证。")


# ========== 驱动装配区 ==========

def setup_browser():
    if not COOKIE: return None

    chrome_options = uc.ChromeOptions()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    
    if HEADLESS:
        chrome_options.add_argument("--headless=new")
    
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

    # 强行对齐驱动主版本号，防止越级爆炸
    chrome_major = get_chrome_major_version()
    kwargs = {"options": chrome_options, "use_subprocess": True}
    if chrome_major:
        logging.info(f"📌 系统真实 Chrome 主版本: [{chrome_major}]，执行强行对齐锁死。")
        kwargs["version_main"] = chrome_major
    else:
        logging.warning("⚠️ 未能匹配到系统 Chrome 版本，将采用默认配置。")

    try:
        driver = uc.Chrome(**kwargs)
    except Exception as e:
        logging.error(f"❌ 驱动引擎建立失败: {e}")
        return None

    # 第一阶段：注入鉴权 Cookie 隔离
    logging.info(">>> [01] 登录域安全身份挂载中...")
    driver.get("https://www.nodeseek.com")
    
    for item in COOKIE.split(";"):
        item = item.strip()
        if not item or "=" not in item: continue
        try:
            name, value = item.split("=", 1)
            driver.add_cookie({"name": name.strip(), "value": value.strip(), "domain": ".nodeseek.com", "path": "/"})
        except: 
            pass

    # 第二阶段：直插控制中心
    logging.info(">>> [02] 正在横向切入后端面板区...")
    driver.get("https://www.nodeseek.com/board")
    
    try:
        wait_for_element_safely(driver, By.CSS_SELECTOR, ".head-info > div", timeout=55, step_name="主控制板防线")
        return driver
    except Exception as e:
        logging.error(f"❌ 初始化链路断开: {e}")
        try: driver.quit()
        except: pass
        return None


# ========== 生产线执行主体 ==========

if __name__ == "__main__":
    logging.info("================ NodeSeek 伪装者协议启动 ================")
    driver = setup_browser()
    if not driver: exit(1)

    try:
        head_info_div = driver.find_element(By.CSS_SELECTOR, ".head-info > div")
        buttons = head_info_div.find_elements(By.TAG_NAME, "button")
        
        if not buttons:
            logging.info(f"✅ 今日签到指标已完成。回执信息: {head_info_div.text.strip()}")
        else:
            logging.info(">>> [03] 锁定未交互实体，准备发起物理聚焦...")
            button = head_info_div.find_element(By.Xpath, ".//button[text()='鸡腿 x 5']") if SIGN_MODE == "chicken" else head_info_div.find_element(By.XPATH, ".//button[text()='试试手气']")
            
            # 优雅地将按钮滚至视口中央
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", button)
            time.sleep(1.5)
            
            button.click()
            logging.info("🎯 业务签到脉冲已成功发射")
            time.sleep(5)
            
            # 使用单引号规避 f-string 解析陷阱
            logging.info(f"🎉 最终控制台状态: {driver.find_element(By.CSS_SELECTOR, '.head-info > div').text.strip()}")

    except Exception as e:
        logging.error(f"❌ 运行时核心崩溃: {e}")
    finally:
        try: 
            driver.quit()
        except: 
            pass
