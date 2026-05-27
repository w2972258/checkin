# -*- coding: utf-8 -*-
# -------------------------------
# NodeSeek 自动签到脚本 (全拟真人类行为学·动态轨迹版)
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
from selenium.webdriver.common.action_chains import ActionChains


# ========== 环境变量 ==========

COOKIE = os.environ.get("NS_COOKIE", "").strip()
SIGN_MODE = os.environ.get("NS_SIGN_MODE", "chicken").strip().lower()
ENABLE_SCREENSHOT = os.environ.get("NS_ENABLE_SCREENSHOT", "true").lower() == "true"

# 【致命警示】如果条件允许，请在 Actions 以外环境配置 HEADLESS = False 测试
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


def take_snapshot(driver, name_suffix):
    if not ENABLE_SCREENSHOT: return
    try:
        ts = datetime.now().strftime("%H%M%S")
        path = SCREENSHOT_DIR / f"step_{ts}_{name_suffix}.png"
        driver.save_screenshot(str(path))
        logging.info(f"📸 [快照] -> {path.name}")
    except Exception as e: logging.debug(f"快照失败: {e}")


# ========== 【人类行为模拟器】核心算法 ==========

def calculate_bezier_point(p0, p1, p2, p3, t):
    """
    计算三次贝塞尔曲线公式中的点位，用于模拟生物运动的加速度与减速度
    """
    x = (1-t)**3 * p0[0] + 3*(1-t)**2 * t * p1[0] + 3*(1-t) * t**2 * p2[0] + t**3 * p3[0]
    y = (1-t)**3 * p0[1] + 3*(1-t)**2 * t * p1[1] + 3*(1-t) * t**2 * p2[1] + t**3 * p3[1]
    return x, y

def human_mouse_move(driver, actions, start_x, start_y, end_x, end_y):
    """
    全拟真人类鼠标轨迹生成：加入控制点、随机抖动、变频延迟
    """
    logging.info(f"🖱️ 启动人类轨迹引擎: ({start_x}, {start_y}) ----> ({end_x}, {end_y})")
    
    # 1. 随机生成两个符合人类拉动习惯的非线性中间控制点
    control_p1 = (
        start_x + (end_x - start_x) * random.uniform(0.1, 0.4) + random.randint(-30, 30),
        start_y + (end_y - start_y) * random.uniform(0.1, 0.4) + random.randint(-30, 30)
    )
    control_p2 = (
        start_x + (end_x - start_x) * random.uniform(0.6, 0.9) + random.randint(-20, 20),
        start_y + (end_y - start_y) * random.uniform(0.6, 0.9) + random.randint(-20, 20)
    )
    
    # 2. 动态步数（距离越长步数越多，模拟真实移动耗时）
    distance = math.sqrt((end_x - start_x)**2 + (end_y - start_y)**2)
    steps = int(max(25, min(60, distance / random.uniform(8, 15))))
    
    current_x, current_y = start_x, start_y
    
    for i in range(steps + 1):
        t = i / steps
        # 三次贝塞尔曲线插值
        target_x, target_y = calculate_bezier_point(
            (start_x, start_y), control_p1, control_p2, (end_x, end_y), t
        )
        
        # 加上微小肌肉颤动（震颤噪音）
        if i < steps:
            target_x += random.uniform(-1.0, 1.0)
            target_y += random.uniform(-1.0, 1.0)
            
        # 计算偏移增量
        offset_x = int(target_x - current_x)
        offset_y = int(target_y - current_y)
        
        if offset_x != 0 or offset_y != 0:
            actions.move_by_offset(offset_x, offset_y)
            current_x += offset_x
            current_y += offset_y
            
        # 变频延迟：前中段快，后段接近目标时出现“对准减速”与微调
        if t < 0.2:
            time.sleep(random.uniform(0.015, 0.03))
        elif t > 0.8:
            time.sleep(random.uniform(0.025, 0.05)) # 减速期
        else:
            time.sleep(random.uniform(0.006, 0.015)) # 爆发期

    # 3. 到达后的微幅犹豫与二次微调 (人类修正视线习惯)
    actions.pause(random.uniform(0.15, 0.35))
    jitter_x = random.choice([-1, 1]) * random.randint(1, 2)
    jitter_y = random.choice([-1, 1]) * random.randint(1, 2)
    actions.move_by_offset(jitter_x, jitter_y)
    actions.pause(random.uniform(0.08, 0.15))
    actions.move_by_offset(-jitter_x, -jitter_y)
    actions.perform()
    logging.info("🎯 贝塞尔轨迹运动完成，进入目标停滞区")


# ========== 毫秒级去负载看门狗 ==========

def wait_for_element_safely(driver, by, value, timeout=60, step_name="未知"):
    logging.info(f"🔍 [看门狗] 搜寻 [{value}] | 阶段: {step_name}")
    start_time = time.time()
    
    # 模拟鼠标初始停泊位置（比如屏幕左上角的某个随机安全区）
    actions = ActionChains(driver)
    current_mouse_x = random.randint(10, 50)
    current_mouse_y = random.randint(10, 50)
    try:
        actions.move_to_element_with_offset(driver.find_element(By.TAG_NAME, "body"), current_mouse_x, current_mouse_y).perform()
    except: pass

    while time.time() - start_time < timeout:
        # 通道1：检测业务层
        try:
            elements = driver.find_elements(by, value)
            if elements and elements[0].is_displayed():
                if value == ".head-info > div" and elements[0].text.strip() == "Loading": pass
                else: return elements[0]
        except: pass

        # 通道2：捕捉 Cloudflare 盾踪迹
        try:
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for idx, iframe in enumerate(iframes):
                ifr_id = iframe.get_attribute("id") or ""
                ifr_src = iframe.get_attribute("src") or ""
                
                if "cloudflare" not in ifr_src and "challenge" not in ifr_src and "cloudflare" not in ifr_id:
                    continue
                
                # 读取宿主层级下的物理盒模型
                iframe_box = driver.execute_script("""
                    var rect = arguments[0].getBoundingClientRect();
                    return {x: rect.left, y: rect.top, width: rect.width, height: rect.height};
                """, iframe)
                
                if not iframe_box or iframe_box['width'] == 0 or iframe_box['height'] == 0:
                    continue

                # 穿透到 Iframe 内部寻靶
                driver.switch_to.frame(iframe)
                pos = driver.execute_script("""
                    function findBox(root) {
                        if (!root) return null;
                        let selectors = ['input[type="checkbox"]', '.ctp-checkbox-label', '.checkmark', '#challenge-stage'];
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
                driver.switch_to.default_content() # 火速撤回主域

                if pos:
                    # 计算最终的合成大视口像素级坐标
                    click_x = int(iframe_box['x'] + pos['x'] + random.uniform(-3, 3))
                    click_y = int(iframe_box['y'] + pos['y'] + random.uniform(-3, 3))
                    
                    logging.info(f"🚨 [发现死盾] 复合锁定的绝对物理坐标 -> X: {click_x}, Y: {click_y}")
                    take_snapshot(driver, "before_human_click")
                    
                    # 【核心修正】：严禁使用 CDP 直接瞬移点击，采用 ActionChains 做高阶生物演练
                    actions = ActionChains(driver)
                    
                    # 1. 人类滑动至复选框并做停顿抖动
                    human_mouse_move(driver, actions, current_mouse_x, current_mouse_y, click_x, click_y)
                    
                    # 2. 模拟真人的点击压迫与释放（增加随机停滞，产生 pointerdown/pointerup 时间差）
                    actions = ActionChains(driver)
                    actions.click_and_hold()
                    actions.pause(random.uniform(0.06, 0.12)) # 避开机器人的固定无时间差按压
                    actions.release()
                    actions.perform()
                    
                    logging.info("💥 [演练完毕] 伪装行为脉冲已发射，等待防线判定...")
                    time.sleep(7)
                    take_snapshot(driver, "after_human_click")
                    
                    # 更新鼠标最后坐标，方便后续进行连续性追踪
                    current_mouse_x, current_mouse_y = click_x, click_y
                    break
        except: pass
        time.sleep(0.6)

    take_snapshot(driver, "fatal_timeout")
    raise TimeoutError("即使注入了生物轨迹，环境指纹/IP固有信用分依然过低，防线未予放行。")


# ========== 浏览器初始化逻辑 ==========

def setup_browser():
    if not COOKIE: return None

    chrome_options = uc.ChromeOptions()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # 掩盖自动化特征
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    if HEADLESS:
        chrome_options.add_argument("--headless=new")
    
    # 动态伪造常见的桌面端 UA
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

    try:
        driver = uc.Chrome(options=chrome_options, use_subprocess=True)
    except Exception as e:
        logging.error(f"引擎启动失败: {e}")
        return None

    # 直切板级主域挂载身份
    logging.info(">>> [01] 进入主域挂载身份隔离区...")
    driver.get("https://www.nodeseek.com")
    
    for item in COOKIE.split(";"):
        item = item.strip()
        if not item or "=" not in item: continue
        try:
            name, value = item.split("=", 1)
            driver.add_cookie({"name": name.strip(), "value": value.strip(), "domain": ".nodeseek.com", "path": "/"})
        except: pass

    # 携 Cookie 直捣黄龙，略过首页刷新节点
    logging.info(">>> [02] 越过首页，直接切入内部签到面板...")
    driver.get("https://www.nodeseek.com/board")
    
    try:
        wait_for_element_safely(driver, By.CSS_SELECTOR, ".head-info > div", timeout=55, step_name="控制面板盾拦截")
        return driver
    except Exception as e:
        logging.error(f"❌ 流程中断: {e}")
        driver.quit()
        return None


if __name__ == "__main__":
    logging.info("================ NodeSeek 伪装者协议启动 ================")
    driver = setup_browser()
    if not driver: exit(1)

    try:
        head_info_div = driver.find_element(By.CSS_SELECTOR, ".head-info > div")
        buttons = head_info_div.find_elements(By.TAG_NAME, "button")
        
        if not buttons:
            logging.info(f"✅ 今日已打卡。当前回执: {head_info_div.text.strip()}")
        else:
            logging.info(">>> [03] 捕获未完成交互实体，开始执行人类聚焦策略...")
            button = head_info_div.find_element(By.XPATH, ".//button[text()='鸡腿 x 5']") if SIGN_MODE == "chicken" else head_info_div.find_element(By.XPATH, ".//button[text()='试试手气']")
            
            # 使用原生平滑滚动代替硬性骤变
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", button)
            time.sleep(1.5)
            
            # 按钮聚焦点击
            button.click()
            logging.info("🎯 业务章签发指令已传递。")
            time.sleep(5)
            logging.info(f"🎉 最终控制台状态: {driver.find_element(By.CSS_SELECTOR, '.head-info > div').text.strip()}")

    except Exception as e:
        logging.error(f"异常崩溃: {e}")
    finally:
        try: driver.quit()
        except: pass
