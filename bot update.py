import json
import time
import telebot
import requests
import os
from datetime import datetime

# УЛУЧШЕННОЕ ЧТЕНИЕ КЛЮЧЕЙ
def get_keys():
    telegram = keys.get("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_TOKEN")
    groq = keys.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY")
    
    # 1. Проверяем файл
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
    
    # 2. Проверяем переменные окружения (для хостинга)
    if not keys["TELEGRAM_TOKEN"]:
        keys["TELEGRAM_TOKEN"] = os.getenv("TELEGRAM_TOKEN")
    if not keys["GROQ_API_KEY"]:
        keys["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY")
    
    return keys["TELEGRAM_TOKEN"], keys["GROQ_API_KEY"]

TOKEN, GROQ_KEY = get_keys()

if not TOKEN:
    print("❌ ОШИБКА: Нет токена телеграм!")
    print("   Добавьте в secret.txt: TELEGRAM_TOKEN=ваш_токен")
    exit()

print("🤖 Бот запускается...")

# ====== УЛУЧШЕННАЯ ПАМЯТЬ ======
MEMORY_FILE = "bot_memory.json"
LOG_FILE = "bot_log.txt"

def log_event(user_id, event_type, details=""):
    """Логирование действий"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] user:{user_id} {event_type} {details}\n")

def load_memory():
    """Загрузка памяти с восстановлением при ошибке"""
    if not os.path.exists(MEMORY_FILE):
        return {}
    
    backup_file = f"{MEMORY_FILE}.backup"
    
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Автоматическое создание резервной копии
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return data
    except Exception as e:
        print(f"⚠️ Ошибка загрузки памяти: {e}")
        
        # Пытаемся восстановить из резервной копии
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
    """Сохраняем память с обработкой ошибок"""
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ Ошибка сохранения памяти: {e}")

memory = load_memory()
print(f"📊 Загружено {sum(len(v) for v in memory.values())} сообщений от {len(memory)} пользователей")

# ====== ИНТЕЛЛЕКТУАЛЬНАЯ ПАМЯТЬ ======
def add_to_memory(user_id, question, answer, model_used=None):
    """Добавляем в память с метаданными"""
    uid = str(user_id)
    
    if uid not in memory:
        memory[uid] = []
    
    memory[uid].append({
        "в": question[:2048],  # Ограничиваем длину вопроса
        "о": answer[:2048],    # Ограничиваем длину ответа
        "т": time.time(),
        "д": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "м": model_used or "llama-3.3-70b-versatile"
    })
    
    # Храним только последние 30 сообщений на пользователя
    if len(memory[uid]) > 30:
        memory[uid] = memory[uid][-30:]
    
    # Сохраняем не каждый раз, а с задержкой (оптимизация)
    if len(memory[uid]) % 5 == 0:  # Каждое 5-е сообщение
        save_memory(memory)
    
    log_event(user_id, "chat", f"q:{len(question)} a:{len(answer)}")

def get_user_history(user_id, limit=5):
    """Получаем историю пользователя"""
    uid = str(user_id)
    if uid in memory:
        return memory[uid][-limit:]
    return []

def get_context_from_history(user_id):
    """Формируем контекст для модели из истории"""
    history = get_user_history(user_id, limit=3)  # Берем 3 последних
    
    if not history:
        return ""
    
    context = "Өткен сөйлесулеріміз (предыдущие разговоры):\n"
    for i, h in enumerate(history, 1):
        context += f"{i}. Мен: {h['в']}\n"
        context += f"   Сіз: {h['о'][:100]}...\n"
    
    return context

# ====== УЛУЧШЕННЫЙ AI МОДУЛЬ ======
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
        """Переключаемся на следующую модель если текущая не работает"""
        self.current_model_index = (self.current_model_index + 1) % len(self.available_models)
        return self.available_models[self.current_model_index]
    
    def ask_with_fallback(self, text, user_lang="mixed"):
        """Запрос к AI с переключением моделей при ошибках"""
        
        # Определяем язык запроса для лучшего ответа
        lang_hint = ""
        if any(char in text for char in "әғқңөұүіӘҒҚҢӨҰҮІ"):
            lang_hint = "Сәлеметсіз бе! Сіз қазақ тілінде сұрақ қойдыңыз. "
            lang_hint += "Жауабыңызды қазақ тілінде беріңіз, егер сұрақ орыс тілінде болса, онда орыс тілінде жауап беріңіз.\n\n"
        elif any(char in text for char in "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"):
            lang_hint = "Здравствуйте! Ваш вопрос на русском. Отвечу на русском языке.\n\n"
        
        # Формируем промпт с учетом языка
        enhanced_prompt = f"{lang_hint}{text}"
        
        for attempt in range(2):  # Пробуем 2 раза с разными моделями
            current_model = self.available_models[self.current_model_index]
            
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {GROQ_KEY}",
                "Content-Type": "application/json"
            }
            
            # Улучшенный промпт для казахского
            system_message = {
                "role": "system",
                "content": "Сіз қазақ және орыс тілдерінде сөйлейтін көмекшісіз. "
                          "Егер сұрақ қазақ тілінде болса, қазақ тілінде жауап беріңіз. "
                          "Егер орыс тілінде болса, орыс тілінде жауап беріңіз. "
                          "Жауаптарыңыз пайдалы және мейірімді болсын."
            }
            
            data = {
                "model": current_model,
                "messages": [
                    system_message,
                    {"role": "user", "content": enhanced_prompt}
                ],
                "max_tokens": 2048,
                "temperature": 0.7,
                "top_p": 0.9
            }
            
            try:
                resp = requests.post(url, headers=headers, json=data, timeout=15)
                
                if resp.status_code == 200:
                    response_data = resp.json()
                    answer = response_data["choices"][0]["message"]["content"]
                    
                    # Проверяем качество ответа на казахском
                    if any(char in text for char in "әғқңөұүіӘҒҚҢӨҰҮІ"):
                        # Если вопрос на казахском, но ответ слишком короткий или не содержит казахских букв
                        if len(answer) < 10 or not any(char in answer for char in "әғқңөұүіӘҒҚҢӨҰҮІ"):
                            print(f"⚠️ Модель {current_model} плохо отвечает на казахском, пробую другую...")
                            self.get_next_model()
                            continue
                    
                    # Считаем использование токенов
                    tokens_used = response_data.get("usage", {}).get("total_tokens", 0)
                    log_event("system", "api_success", f"model:{current_model} tokens:{tokens_used}")
                    
                    return answer, current_model
                
                elif resp.status_code == 429:
                    print(f"⚠️ Лимит запросов для {current_model}, пробую другую...")
                    time.sleep(0.5)
                    self.get_next_model()
                    continue
                    
                elif resp.status_code == 404:
                    print(f"⚠️ Модель {current_model} недоступна, переключаюсь...")
                    self.get_next_model()
                    continue
                    
                else:
                    print(f"❌ Ошибка {resp.status_code} для {current_model}: {resp.text[:100]}")
            
            except requests.exceptions.Timeout:
                print(f"⌛ Таймаут для {current_model}")
            except Exception as e:
                print(f"❌ Ошибка запроса: {e}")
            
            # Пробуем следующую модель
            self.get_next_model()
            time.sleep(0.3)
        
        # Если все модели не сработали
        self.fallback_count += 1
        
        # Запасной ответ на казахском/русском
        fallback_responses = [
            "Кешіріңіз, қазір жауап бере алмаймын. Біраздан соң қайталап көріңіз. 😊",
            "Извините, сейчас не могу ответить. Попробуйте через некоторое время. 😊",
            "Қазір серверде қиындық бар. Біраздан кейін сұраңыз. 🙏"
        ]
        
        return fallback_responses[self.fallback_count % len(fallback_responses)], "fallback"

# Инициализируем AI модуль
ai_module = AIModule()

#УЛУЧШЕННЫЙ БОТ 
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start', 'help'])
def start(msg):
    uid = msg.from_user.id
    history = get_user_history(uid)
    history_count = len(history)
    
    welcome_text = (
        "🤖 *Сәлем! / Hello!*\n\n"
        "Мен қазақ және орыс тілдерінде сөйлейтін көмекшімін.\n"
        "Просто напишите вопрос на русском или казахском!\n\n"
        f"📊 Мен сіздің соңғы {history_count} сұрағыңызды есімде сақтаймын\n\n"
        "*Команды / Команды:*\n"
        "/history - Соңғы сұрақтар\n"
        "/clear - Тарихыңызды тазарту\n"
        "/stats - Статистика\n"
        "/model - Ағымдағы модель\n"
        "/lang - Тіл параметрлері\n"
        "/help - Көмек\n\n"
        "Жазған тіліңізге қарай жауап беремін! ✨"
    )
    
    bot.send_message(msg.chat.id, welcome_text, parse_mode='Markdown')
    log_event(uid, "start")

@bot.message_handler(commands=['history'])
def show_history_cmd(msg):
    uid = msg.from_user.id
    history = get_user_history(uid, limit=10)
    
    if not history:
        bot.reply_to(msg, "Әлі тарихыңыз жоқ / История пока пуста")
        return
    
    text = "📜 *Соңғы сұрақтарыңыз / Последние вопросы:*\n\n"
    
    for i, chat in enumerate(reversed(history[-10:]), 1):
        date_str = datetime.fromtimestamp(chat['т']).strftime("%d.%m %H:%M")
        text += f"*{i}.* [{date_str}] {chat['м'][:10]}...\n"
        text += f"   👤: {chat['в'][:50]}...\n"
        text += f"   🤖: {chat['о'][:50]}...\n\n"
    
    bot.send_message(msg.chat.id, text, parse_mode='Markdown')
    log_event(uid, "view_history")

@bot.message_handler(commands=['clear'])
def clear_history(msg):
    uid = str(msg.from_user.id)
    
    if uid in memory and memory[uid]:
        count = len(memory[uid])
        del memory[uid]
        save_memory(memory)
        
        reply_text = f"✅ Тарих тазартылды! {count} хабарлама жойылды.\n"
        reply_text += f"✅ История очищена! Удалено {count} сообщений."
        
        bot.reply_to(msg, reply_text)
        log_event(uid, "clear_history", f"cleared:{count}")
    else:
        bot.reply_to(msg, "Тарихыңыз бос / История уже пуста")

@bot.message_handler(commands=['stats'])
def stats(msg):
    uid = str(msg.from_user.id)
    user_count = len(memory.get(uid, []))
    total_count = sum(len(v) for v in memory.values())
    total_users = len(memory)
    
    # Статистика по моделям
    model_stats = {}
    for user_data in memory.values():
        for msg_data in user_data:
            model = msg_data.get('м', 'unknown')
            model_stats[model] = model_stats.get(model, 0) + 1
    
    stats_text = f"""📊 *Статистика / Statistics:*

👥 Пайдаланушылар / Пользователи: *{total_users}*
💬 Барлық хабарламалар / Все сообщения: *{total_count}*
📨 Сіздің хабарламаларыңыз / Ваши сообщения: *{user_count}*

🤖 *Модельдер бойынша / По моделям:*
"""
    
    for model, count in sorted(model_stats.items(), key=lambda x: x[1], reverse=True):
        stats_text += f"  • {model}: {count}\n"
    
    stats_text += f"\n⚙️ *Ағымдағы модель / Текущая модель:* {ai_module.available_models[ai_module.current_model_index]}"
    
    bot.send_message(msg.chat.id, stats_text, parse_mode='Markdown')
    log_event(uid, "view_stats")

@bot.message_handler(commands=['model'])
def model_info(msg):
    current = ai_module.available_models[ai_module.current_model_index]
    all_models = "\n".join([f"  • {m}" + (" ✅" if m == current else "") for m in ai_module.available_models])
    
    text = f"""🤖 *Модель ақпараты / Model info:*

Ағымдағы / Текущая: *{current}*

Барлық қолжетімді модельдер / Все доступные модели:
{all_models}

Автоматты түрде ең жақсы жұмыс істейтін модель таңдалады.
"""
    
    bot.reply_to(msg, text, parse_mode='Markdown')

@bot.message_handler(commands=['lang'])
def lang_settings(msg):
    text = """🌍 *Тіл параметрлері / Language settings:*

Бот сіздің сұрағыңыздың тіліне қарай автоматты түрде жауап береді.

Егер сұрақ қазақ тілінде болса:
  → Жауап қазақ тілінде болады

Егер сұрақ орыс тілінде болса:
  → Жауап орыс тілінде болады

Егер аралас сұрақ болса:
  → Негізгі тілде жауап, қажет болса аударма қосады

Қазіргі уақытта қолданыстағы модель: *{model}*

Сұрақ қойып көріңіз! 😊
""".format(model=ai_module.available_models[ai_module.current_model_index])
    
    bot.reply_to(msg, text, parse_mode='Markdown')

@bot.message_handler(func=lambda m: True)
def handle_message(msg):
    if msg.text.startswith('/'):
        bot.reply_to(msg, "Белгісіз команда / Неизвестная команда")
        return
    
    uid = msg.from_user.id
    question = msg.text.strip()
    
    # Проверка длины
    if len(question) < 2:
        bot.reply_to(msg, "Өте қысқа / Слишком коротко")
        return
    
    if len(question) > 2000:
        bot.reply_to(msg, "Өте ұзын (2000 таңбадан аспауы керек) / Слишком длинно (макс 2000 символов)")
        return
    
    # Показываем "печатает..."
    bot.send_chat_action(msg.chat.id, 'typing')
    
    # Добавляем контекст из истории
    context = get_context_from_history(uid)
    full_question = f"{context}\n\nЖаңа сұрақ / Новый вопрос: {question}"
    
    # Получаем ответ от AI
    answer, model_used = ai_module.ask_with_fallback(full_question)
    
    # Сохраняем в память
    add_to_memory(uid, question, answer, model_used)
    
    # Отправляем ответ
    try:
        # Если ответ очень длинный, разбиваем на части
        if len(answer) > 3000:
            for i in range(0, len(answer), 3000):
                chunk = answer[i:i+3000]
                if i == 0:
                    bot.reply_to(msg, chunk)
                else:
                    bot.send_message(msg.chat.id, chunk)
        else:
            bot.reply_to(msg, answer)
            
        # Логируем успешный ответ
        log_event(uid, "reply_sent", f"q_len:{len(question)} a_len:{len(answer)} model:{model_used}")
        
    except Exception as e:
        error_msg = "Кешіріңіз, жауап жіберуде қате пайда болды / Извините, ошибка при отправке ответа"
        bot.reply_to(msg, error_msg)
        log_event(uid, "reply_error", str(e)[:100])

#АВТОСОХРАНЕНИЕ ПАМЯТ
import threading

def auto_save_memory():
    """Автосохранение памяти каждые 5 минут"""
    while True:
        time.sleep(300)  # 5 минут
        if memory:
            save_memory(memory)
            print(f"💾 Автосохранение памяти: {len(memory)} пользователей")

# Запускаем автосохранение в отдельном потоке
save_thread = threading.Thread(target=auto_save_memory, daemon=True)
save_thread.start()

# ЗАПУСК БОТА
print("=" * 50)
print("🚀 Бот успешно запущен!")
print(f"🤖 Доступные модели: {', '.join(ai_module.available_models)}")
print(f"💾 Память: {MEMORY_FILE}")
print(f"📝 Логи: {LOG_FILE}")
print("=" * 50)

try:
    bot.polling(none_stop=True, interval=0, timeout=20)
except Exception as e:
    print(f"❌ Критическая ошибка бота: {e}")
    # Сохраняем память перед выходом
    save_memory(memory)
