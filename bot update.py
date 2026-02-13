import json
import time
import telebot
import requests
import os
from datetime import datetime
from flask import Flask
from threading import Thread
import threading

#Flask для UptimeRobot
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host="0.0.0.0", port=3000)

t = Thread(target=run, daemon=True)
t.start()

#Чтение ключей из secret.txt
def get_keys():
    keys = {"TELEGRAM_TOKEN": None, "GROQ_API_KEY": None}
    
    if os.path.exists("secret.txt"):
        try:
            with open("secret.txt", "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        if key in keys:
                            keys[key] = value.strip()
        except Exception as e:
            print(f"⚠️ Ошибка чтения secret.txt: {e}")
    
    if not keys["TELEGRAM_TOKEN"]:
        keys["TELEGRAM_TOKEN"] = os.getenv("TELEGRAM_TOKEN")
    if not keys["GROQ_API_KEY"]:
        keys["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY")
    
    return keys["TELEGRAM_TOKEN"], keys["GROQ_API_KEY"]

TOKEN, GROQ_KEY = get_keys()

if not TOKEN:
    print("❌ ОШИБКА: Нет токена телеграм!")
    exit()

bot = telebot.TeleBot(TOKEN)
@bot.message_handler(commands=['ping'])
def ping(message):
    bot.reply_to(message, "🏓 Pong!")
# Память и логирование
MEMORY_FILE = "bot_memory.json"
LOG_FILE = "bot_log.txt"

def log_event(user_id, event_type, details=""):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] user:{user_id} {event_type} {details}\n")

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {}
    backup_file = f"{MEMORY_FILE}.backup"
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return data
    except Exception as e:
        print(f"⚠️ Ошибка загрузки памяти: {e}")
        if os.path.exists(backup_file):
            try:
                with open(backup_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                print("✅ Восстановлено из резервной копии")
                return data
            except:
                pass
        return {}

def save_memory(data):
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ Ошибка сохранения памяти: {e}")

memory = load_memory()

def add_to_memory(user_id, question, answer, model_used=None):
    uid = str(user_id)
    if uid not in memory:
        memory[uid] = []
    memory[uid].append({
        "в": question[:2048],
        "о": answer[:2048],
        "т": time.time(),
        "д": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "м": model_used or "llama-3.3-70b-versatile"
    })
    if len(memory[uid]) > 30:
        memory[uid] = memory[uid][-30:]
    if len(memory[uid]) % 5 == 0:
        save_memory(memory)
    log_event(user_id, "chat", f"q:{len(question)} a:{len(answer)} model:{model_used}")

def get_user_history(user_id, limit=5):
    uid = str(user_id)
    if uid in memory:
        return memory[uid][-limit:]
    return []

def get_context_from_history(user_id):
    history = get_user_history(user_id, limit=3)
    if not history:
        return ""
    context = "Өткен сөйлесулеріміз (предыдущие разговоры):\n"
    for i, h in enumerate(history, 1):
        context += f"{i}. Мен: {h['в']}\n   Сіз: {h['о'][:100]}...\n"
    return context

#AI Модуль
class AIModule:
    def __init__(self):
        self.available_models = [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
            "llama-3.2-3b-preview"
        ]
        self.current_model_index = 0
        self.fallback_count = 0

    def get_next_model(self):
        self.current_model_index = (self.current_model_index + 1) % len(self.available_models)
        return self.available_models[self.current_model_index]

    def ask_with_fallback(self, text):
        lang_hint = ""
        if any(char in text for char in "әғқңөұүіӘҒҚҢӨҰҮІ"):
            lang_hint = "Сәлеметсіз бе! Сіз қазақ тілінде сұрақ қойдыңыз. Жауабыңызды қазақ тілінде беріңіз.\n\n"
        elif any(char in text for char in "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"):
            lang_hint = "Здравствуйте! Ваш вопрос на русском. Отвечу на русском языке.\n\n"
        enhanced_prompt = f"{lang_hint}{text}"
        for attempt in range(2):
            current_model = self.available_models[self.current_model_index]
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
            system_message = {"role": "system", "content": "Вы ассистент, отвечающий на казахском и русском."}
            data = {"model": current_model, "messages":[system_message, {"role":"user","content":enhanced_prompt}], "max_tokens":100000, "temperature":0.7, "top_p":0.9}
            try:
                resp = requests.post(url, headers=headers, json=data, timeout=15)
                if resp.status_code == 200:
                    answer = resp.json()["choices"][0]["message"]["content"]
                    return answer, current_model
                else:
                    self.get_next_model()
                    time.sleep(0.3)
            except:
                self.get_next_model()
                time.sleep(0.3)
        # fallback
        fallback_responses = ["Кешіріңіз, қазір жауап бере алмаймын. Біраздан соң қайталап көріңіз. 😊",
                              "Извините, сейчас не могу ответить. Попробуйте через некоторое время. 😊",
                              "Қазір серверде қиындық бар. Біраздан кейін сұраңыз. 🙏"]
        self.fallback_count += 1
        return fallback_responses[self.fallback_count % len(fallback_responses)], "fallback"

ai_module = AIModule()

#Обработчики бота
@bot.message_handler(commands=['start', 'help'])
def start_msg(msg):
    uid = msg.from_user.id
    history_count = len(get_user_history(uid))
    welcome_text = (
        f"🤖 *Сәлем! / Hello!*\n\n"
        f"Мен қазақ және орыс тілдерінде сөйлейтін көмекшімін.\n"
        f"Сіздің соңғы {history_count} сұрағыңызды есімде сақтаймын.\n"
        f"/history - соңғы сұрақтар\n/clear - история тазалау\n/stats - статистика\n/model - модель\n/lang - тіл\n/help - помощь"
    )
    bot.send_message(msg.chat.id, welcome_text, parse_mode='Markdown')
    log_event(uid, "start")

@bot.message_handler(func=lambda m: True)
def handle_message(msg):
    if msg.text.startswith('/'):
        bot.reply_to(msg, "Белгісіз команда / Неизвестная команда")
        return
    uid = msg.from_user.id
    question = msg.text.strip()
    if len(question) < 2:
        bot.reply_to(msg, "Өте қысқа / Слишком коротко")
        return
    bot.send_chat_action(msg.chat.id, 'typing')
    context = get_context_from_history(uid)
    full_question = f"{context}\n\nЖаңа сұрақ / Новый вопрос: {question}"
    answer, model_used = ai_module.ask_with_fallback(full_question)
    add_to_memory(uid, question, answer, model_used)
    bot.reply_to(msg, answer)

#Автосохранение памяти
def auto_save_memory():
    while True:
        time.sleep(300)
        if memory:
            save_memory(memory)
            print(f"💾 Автосохранение памяти: {len(memory)} пользователей")
save_thread = threading.Thread(target=auto_save_memory, daemon=True)
save_thread.start()

#Запуск бота
print("🚀 Бот успешно запущен!")
bot.infinity_polling()
