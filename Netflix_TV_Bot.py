import telebot
import os
import re
import threading
import time
from playwright.sync_api import sync_playwright
from http.server import HTTPServer, BaseHTTPRequestHandler

# --- HUGGING FACE PORT 7860 TRICK ---
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

def run_dummy_server():
    server = HTTPServer(('0.0.0.0', 7860), DummyHandler)
    server.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()
# ------------------------------------
# ==========================================
# CONFIG
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7968768710:AAFpox3IBejKkEU0Z8wIlRNjg05tOO0SAa0")
bot = telebot.TeleBot(BOT_TOKEN)

user_sessions = {}

def parse_netscape_cookies(content):
    """Convert Netscape cookie format to Playwright cookie format"""
    cookies = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        parts = line.split("\t")
        if len(parts) >= 7:
            domain = parts[0]
            # Playwright requires domains to start with '.' if they are subdomains
            if not domain.startswith("."):
                domain = "." + domain
            cookies.append({
                "name": parts[5],
                "value": parts[6],
                "domain": domain,
                "path": parts[2]
            })
    return cookies

@bot.message_handler(commands=["start"])
def start(msg):
    bot.send_message(msg.chat.id, 
        "📺 **Netflix TV Code Approver Bot** 📺\n\n"
        "1️⃣ Send me a Netscape **cookie file** (`.txt`)\n"
        "2️⃣ Send me the 8-digit **TV Code**\n"
        "3️⃣ I will log you in on your TV instantly! 🚀", 
        parse_mode="Markdown")

@bot.message_handler(content_types=["document"])
def handle_cookie_file(msg):
    chat_id = msg.chat.id
    fname = msg.document.file_name.lower()
    
    if not fname.endswith(".txt"):
        bot.reply_to(msg, "❌ Please send a valid `.txt` cookie file.")
        return

    status_msg = bot.reply_to(msg, "⏳ Downloading cookies...")
    
    try:
        file_info = bot.get_file(msg.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        content = downloaded_file.decode("utf-8")
        
        cookies = parse_netscape_cookies(content)
        if not cookies:
            bot.edit_message_text("❌ No valid Netflix cookies found in the file.", chat_id, status_msg.message_id)
            return
            
        user_sessions[chat_id] = {"cookies": cookies}
        bot.edit_message_text(
            "✅ **Cookies Saved!**\n\n"
            "📺 Now send me the 8-digit TV code you see on your screen (e.g., `1234-5678` or `12345678`):", 
            chat_id, status_msg.message_id, parse_mode="Markdown"
        )
    except Exception as e:
        bot.edit_message_text(f"❌ Error: {e}", chat_id, status_msg.message_id)

@bot.message_handler(content_types=["text"])
def handle_tv_code(msg):
    chat_id = msg.chat.id
    text = msg.text.strip()
    
    if chat_id not in user_sessions or not user_sessions[chat_id].get("cookies"):
        bot.reply_to(msg, "❌ Please send a cookie file first.")
        return
        
    # Clean the code (remove spaces/dashes)
    code = re.sub(r'[^a-zA-Z0-9]', '', text)
    if len(code) != 8:
        bot.reply_to(msg, "❌ Invalid TV code. It must be exactly 8 characters long.")
        return
        
    status_msg = bot.reply_to(msg, "🚀 Opening Netflix and entering code...")
    threading.Thread(target=approve_tv_code, args=(chat_id, user_sessions[chat_id]["cookies"], code, status_msg.message_id)).start()

def approve_tv_code(chat_id, cookies, code, msg_id):
    try:
        with sync_playwright() as p:
            bot.edit_message_text("🌐 Starting invisible browser...", chat_id, msg_id)
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            # Set cookies
            context.add_cookies(cookies)
            page = context.new_page()
            
            bot.edit_message_text("🔄 Navigating...", chat_id, msg_id)
            page.goto("https://www.netflix.com/tv8", wait_until="domcontentloaded", timeout=15000)
            
            # Check if we are logged in
            if "login" in page.url or "signup" in page.url:
                bot.edit_message_text("❌ Cookies are **expired**.", chat_id, msg_id, parse_mode="Markdown")
                browser.close()
                return

            bot.edit_message_text(f"🚀 Entering code: `{code}`...", chat_id, msg_id, parse_mode="Markdown")
            
            # Fill the code extremely fast but correctly
            try:
                # 1. Focus the first input box
                page.locator("input").first.click(timeout=10000)
                # 2. Type the code slowly to trigger React events
                page.keyboard.type(code, delay=100)
                time.sleep(0.5)
                
                # 3. Click the submit button
                submit_btn = page.locator("button[type='submit'], [data-uia='action_submit']").first
                if submit_btn.is_visible():
                    submit_btn.click(timeout=2000)
                else:
                    page.keyboard.press("Enter")
            except Exception as e:
                pass
                
            bot.edit_message_text("⏳ Approving...", chat_id, msg_id)
            time.sleep(4) # Wait for Netflix to process the code
            
            # Check for success message
            content = page.content().lower()
            if "success" in content or "ready" in content or "جاهز" in content or "نجاح" in content or "enjoy" in content:
                bot.edit_message_text("✅ **SUCCESS!** Your TV is now logged in. Enjoy! 🍿🎬", chat_id, msg_id, parse_mode="Markdown")
            else:
                # Take a screenshot to help debug if it fails
                screenshot_path = f"error_{chat_id}.png"
                page.screenshot(path=screenshot_path)
                bot.edit_message_text("⚠️ Code was sent, but Netflix didn't show a clear success message. Please check your TV!", chat_id, msg_id)
                try:
                    with open(screenshot_path, "rb") as photo:
                        bot.send_photo(chat_id, photo, caption="Here is what Netflix showed us:")
                    os.remove(screenshot_path)
                except: pass

            browser.close()
            
    except Exception as e:
        bot.edit_message_text(f"❌ Playwright Error: {e}\n\nMake sure you ran: `playwright install`", chat_id, msg_id)

import time

while True:
    try:
        print("[*] Netflix TV Bot is running...")
        bot.infinity_polling(timeout=60, long_polling_timeout=60, skip_pending=True)
    except Exception as e:
        print(f"Network Error: {e}")
        print("Retrying in 5 seconds...")
        time.sleep(5)
