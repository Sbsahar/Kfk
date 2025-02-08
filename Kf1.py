import telebot
import threading
import requests
from telebot import types
import time
import json
from telebot.types import BotCommand
# توكن البوت ومفتاح API
TOKEN = '8196365414:AAEhieN1AcfDjp2PopggozmnZdqpept97ow'
api_key = "sk_b34dcf68d51bee17991c066ead5eeb94fd72b26d5e73267d096f851420397bfaa1ac6a2482a141cdc8e07565b7a6ca0ddec607f8f5df31c3bc7be55cb6d14ffa024RooBLphN0iXkbKBufH"
CHANNEL_URL = 'https://t.me/SYR_SB'
CHANNEL_USERNAME = 'SYR_SB' 
DEVELOPER_CHAT_ID = '6789179634'
bot = telebot.TeleBot(TOKEN)
users = set()
groups = set()
user_violations = {}
activated_groups = {}  # {group_id: report_chat_id}
daily_reports = {}     # {group_id: {"banned": [], "muted": [], "deleted_content": [], "manual_actions": []}}
gbt_enabled = False
commands = [
    BotCommand('gbt', 'استخدام الذكاء الاصطناعي (GPT)'),
    BotCommand('opengbt', 'تفعيل الذكاء الاصطناعي (للمشرفين فقط)'),
    BotCommand('closegbt', 'تعطيل الذكاء الاصطناعي (للمشرفين فقط)')
]
bot.set_my_commands(commands)
def get_blackbox_response(user_input):
    """ إرسال استفسار إلى Blackbox AI واسترجاع الرد """
    url = "https://api.blackbox.ai/api/chat"
    headers = {
        "Content-Type": "application/json"
    }
    json_data = json.dumps({
        "messages": [{"content": user_input, "role": "user"}],
        "model": "deepseek-ai/DeepSeek-V3",
        "max_tokens": "1024"
    })
    max_retries = 3  
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, data=json_data, timeout=10)  # زيادة المهلة
            print(f"Response Status: {response.status_code}")
            print(f"Response Text: {response.text}")
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"Parsed Response: {data}")
                    return data.get("response", "⚠️ لا يوجد رد متاح.")
                except json.JSONDecodeError:
                    if response.text.strip():
                        return response.text
                    else:
                        return "⚠️ لا يوجد رد متاح."
            else:
                return f"⚠️ خطأ: {response.status_code} - {response.text}"     
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)  
            else:
                return "الخدمة مشغولة حاليًا، يرجى المحاولة مرة أخرى لاحقًا."

def split_message(message, max_length=4096):
    """ تقسيم الرسالة إلى أجزاء إذا كانت طويلة """
    return [message[i:i + max_length] for i in range(0, len(message), max_length)]
def check_gbt_status(chat_id):
    """ التحقق من حالة الذكاء الاصطناعي وإرسال رسالة إذا كان معطلًا """
    global gbt_enabled
    if not gbt_enabled:
        bot.send_message(chat_id, "للأسف، قام المشرفون بتعطيل الذكاء الاصطناعي. يرجى طلب تفعيله من أحد المشرفين.")
        return False
    return True
# ------ دوال تفعيل التقارير ------



def check_image_safety(image_url):
    """فحص إذا كانت الصورة غير مناسبة باستخدام API خارجي"""
    api_url = "https://api.jigsawstack.com/v1/validate/nsfw"
    headers = {
        "x-api-key": api_key
    }
    params = {
        "url": image_url
    }
    try:
        response = requests.get(api_url, headers=headers, params=params)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('nudity', False):
                return 'nude'
            return 'ok'
        else:
            print(f"Error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"An error occurred: {e}")
        return 'error'
def is_user_admin(bot, chat_id, user_id):
    """
    التحقق مما إذا كان المستخدم مشرفًا في المجموعة.
    """
    try:
        admins = bot.get_chat_administrators(chat_id)
        for admin in admins:
            if admin.user.id == user_id:
                return True
        return False
    except Exception as e:
        print(f"Error checking admin status: {e}")
        return False
def extract_user_info(bot, message):
    """
    استخراج الأيدي أو اليوزرنيم من الرسالة.
    """
    if message.reply_to_message:
        return message.reply_to_message.from_user.id, message.reply_to_message.from_user.username
    elif len(message.text.split()) > 1:
        target = message.text.split()[1]
        if target.startswith("@"): 
            try:
                user_info = bot.get_chat(target)
                return user_info.id, user_info.username 
            except Exception as e:
                print(f"Error getting user info: {e}")
                return None, None
        else: 
            try:
                user_id = int(target) 
                return user_id, None  
            except ValueError:
                print("Invalid user ID format")
                return None, None
    else:
        return None, None
def is_user_subscribed(user_id):
    """التحقق من اشتراك المستخدم في القناة"""
    try:
        chat_member = bot.get_chat_member(f"@{CHANNEL_USERNAME}", user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"Error checking subscription: {e}")
        return False
@bot.message_handler(content_types=['left_chat_member'])
def handle_manual_ban(message):
    """تسجيل عمليات الطرد أو الحظر اليدوي وحفظها في التقرير اليومي"""
    chat_id = message.chat.id
    removed_user = message.left_chat_member

    if chat_id in activated_groups:
        user_info = f"👤 الاسم: {removed_user.first_name}\n" \
                    f"📎 اليوزر: @{removed_user.username if removed_user.username else 'لا يوجد'}\n" \
                    f"🆔 الآيدي: <code>{removed_user.id}</code>"

        event = f"🚷 <b>تم طرد أو حظر عضو يدويًا:</b>\n\n{user_info}"

        # ✅ التأكد من وجود سجل للمجموعة
        if chat_id not in daily_reports:
            daily_reports[chat_id] = {
                "banned": [],
                "muted": [],
                "deleted_content": [],
                "manual_actions": []
            }

        # ✅ تسجيل الحدث في التقرير اليومي تحت قسم "الإجراءات اليدوية"
        daily_reports[chat_id]["manual_actions"].append(event)

        # ✅ إرسال إشعار فوري إلى مجموعة التقارير
        report_chat_id = activated_groups[chat_id]
        bot.send_message(report_chat_id, event, parse_mode="HTML")

@bot.message_handler(content_types=['new_chat_members'])
def handle_new_members(message):
    """تسجيل انضمام الأعضاء الجدد (اختياري)"""
    chat_id = message.chat.id
    for member in message.new_chat_members:
        if chat_id in activated_groups:
            user_info = f"👤 الاسم: {member.first_name}\n" \
                        f"📎 اليوزر: @{member.username if member.username else 'لا يوجد'}\n" \
                        f"🆔 الآيدي: <code>{member.id}</code>"

            event = f"✅ <b>انضمام عضو جديد:</b>\n\n{user_info}"
            
            # حفظ الحدث في التقرير اليومي
            daily_reports[chat_id]["manual_actions"].append(event)

            # إرسال إشعار إلى مجموعة التقارير
            report_chat_id = activated_groups[chat_id]
            bot.send_message(report_chat_id, event, parse_mode="HTML")        
        
@bot.message_handler(commands=['enable_reports'])
def activate_reports(message):
    # التحقق من كون المستخدم مشرف
    if not is_user_admin(bot, message.chat.id, message.from_user.id):
        bot.send_message(message.chat.id, "❌ يجب أن تكون مشرفًا في المجموعة لتفعيل التقارير.")
        return

    msg = bot.send_message(message.chat.id, "📝 أرسل ID المجموعة المراد تفعيل التقارير لها.")
    bot.register_next_step_handler(msg, process_group_id_step)

def process_group_id_step(message):
    try:
        group_id = int(message.text.strip())  # تحويل الإدخال إلى رقم
        if not is_user_admin(bot, group_id, message.from_user.id):  # تحقق من المشرف في المجموعة
            bot.send_message(message.chat.id, "❌ يجب أن تكون مشرفًا في المجموعة لتفعيل التقارير.")
            return

        activated_groups[group_id] = message.chat.id
        daily_reports[group_id] = {"banned": [], "muted": [], "deleted_content": [], "manual_actions": []}
        bot.send_message(message.chat.id, f"✅ تم تفعيل التقارير للمجموعة (ID: {group_id})")
        schedule_daily_report(group_id)
    except ValueError:
        bot.send_message(message.chat.id, "❌ يرجى إدخال ID صحيح للمجموعة.")        
        
@bot.message_handler(commands=['gbt'])
def handle_gbt_command(message):
    """ التعامل مع الأمر /gbt """
    if not check_gbt_status(message.chat.id):
        return
    
    user_input = message.text.split('/gbt', 1)[-1].strip()
    if not user_input:
        bot.send_message(message.chat.id, "يرجى إرسال سؤال بعد /gbt")
        return
    
    thinking_message = bot.send_message(message.chat.id, "جاري الاتصال بالذكاء، انتظر قليلًا...", parse_mode="Markdown")
    response = get_blackbox_response(user_input)
    bot.delete_message(message.chat.id, thinking_message.message_id)
    
    message_parts = split_message(response)
    for part in message_parts:
        bot.send_message(message.chat.id, part, parse_mode="Markdown")        
@bot.message_handler(commands=['opengbt'])
def handle_opengbt_command(message):
    """ تفعيل الذكاء الاصطناعي """
    global gbt_enabled
    try:
        # التحقق من أن المستخدم مشرف أو مالك المجموعة
        chat_member = bot.get_chat_member(message.chat.id, message.from_user.id)
        if chat_member.status in ["administrator", "creator"]:
            gbt_enabled = True
            bot.send_message(message.chat.id, "تم تفعيل الذكاء الاصطناعي بنجاح.")
        else:
            bot.send_message(message.chat.id, "عذرًا، فقط المشرفون يمكنهم تفعيل الذكاء الاصطناعي.")
    except Exception as e:
        print(f"Error checking admin status: {e}")
        bot.send_message(message.chat.id, "حدث خطأ أثناء التحقق من الصلاحيات.")        
@bot.message_handler(commands=['closegbt'])
def handle_closegbt_command(message):
    """ تعطيل الذكاء الاصطناعي """
    global gbt_enabled
    try:
        # التحقق من أن المستخدم مشرف أو مالك المجموعة
        chat_member = bot.get_chat_member(message.chat.id, message.from_user.id)
        if chat_member.status in ["administrator", "creator"]:
            gbt_enabled = False
            bot.send_message(message.chat.id, "تم تعطيل الذكاء الاصطناعي بنجاح.")
        else:
            bot.send_message(message.chat.id, "عذرًا، فقط المشرفون يمكنهم تعطيل الذكاء الاصطناعي.")
    except Exception as e:
        print(f"Error checking admin status: {e}")
        bot.send_message(message.chat.id, "حدث خطأ أثناء التحقق من الصلاحيات.")
                
        
@bot.message_handler(commands=['ban'])
def ban_user(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_user_admin(bot, chat_id, user_id):
        bot.reply_to(message, "**عذرًا!**\nهذا الأمر مخصص للمشرفين فقط.\nلا تقم بذلك مرة أخرى هذا أمر خطير", parse_mode="Markdown")
        return
    target_id, target_username = extract_user_info(bot, message)
    if not target_id:
        bot.reply_to(message, "**كيفية استخدام الأمر:**\n"
                              "1. بالرد على رسالة العضو: `/ban`\n"
                              "2. باستخدام الأيدي: `/ban 12345`\n" , parse_mode="Markdown")
        return
    if is_user_admin(bot, chat_id, target_id):
        bot.reply_to(message, "**عذرًا!**\nلا يمكنك حظر مشرف آخر.\nدعك من هذا المزاح", parse_mode="Markdown")
        return
    try:
        bot.ban_chat_member(chat_id, target_id)
        # ------ التعديل الجديد ------
        if chat_id in activated_groups:
            event = f"تم حظر العضو: {target_username or target_id}"
            daily_reports[chat_id]["banned"].append(event)
        # ------ نهاية التعديل ------
        bot.reply_to(message, f"**تم حظر العضو** [{target_username}](tg://user?id={target_id}).\n🚫 لن يتمكن من العودة إلى المجموعة.", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"حدث خطأ أثناء محاولة حظر العضو: {e}")
@bot.message_handler(commands=['unban'])
def unban_user(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_user_admin(bot, chat_id, user_id):
        bot.reply_to(message, "**عذرًا!**\nهذا الأمر مخصص للمشرفين فقط.\nلا تقم بذلك مرة أخرى، هذا أمر خطير", parse_mode="Markdown")
        return
    target_id, target_username = extract_user_info(bot, message)
    if not target_id:
        bot.reply_to(message, "**كيفية استخدام الأمر:**\n"
                              "1. بالرد على رسالة العضو: `/unban`\n"
                              "2. باستخدام الأيدي: `/unban 12345`\n" , parse_mode="Markdown")
        return
    try:
        bot.unban_chat_member(chat_id, target_id)
        bot.reply_to(message, f"**تم إلغاء حظر العضو** [{target_username}](tg://user?id={target_id}).\n"
                              f"🎉 الآن يمكنه الانضمام إلى المجموعة مرة أخرى!", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"حدث خطأ أثناء محاولة إلغاء حظر العضو: {e}")
@bot.message_handler(commands=['mute'])
def mute_user(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # التحقق من أن المستخدم مشرف
    if not is_user_admin(bot, chat_id, user_id):
        bot.reply_to(message, "عذرًا!\nهذا الأمر مخصص للمشرفين فقط.\nلا تقم بذلك مرة أخرى، هذا أمر خطير", parse_mode="HTML")
        return
    
    # استخراج معلومات العضو المستهدف
    target_id, target_username = extract_user_info(bot, message)
    if not target_id:
        bot.reply_to(message, "كيفية استخدام الأمر:\n"
                              "1. بالرد على رسالة العضو: <code>/mute</code>\n"
                              "2. باستخدام الأيدي: <code>/mute 12345</code>\n"
                              "3. لتقييد مؤقت: <code>/mute 12345 30</code> (30 دقيقة مثال)", parse_mode="HTML")
        return
    
    command_parts = message.text.split()
    
    # إذا كان الأمر بالرد على رسالة العضو
    if message.reply_to_message:
        if len(command_parts) > 1:
            try:
                mute_duration = int(command_parts[1])
            except ValueError:
                bot.reply_to(message, "خطأ!\nالمدة الزمنية يجب أن تكون رقمًا صحيحًا.", parse_mode="HTML")
                return
        else:
            mute_duration = None
    else:
        if len(command_parts) > 2:
            try:
                mute_duration = int(command_parts[2])
            except ValueError:
                bot.reply_to(message, "خطأ!\nالمدة الزمنية يجب أن تكون رقمًا صحيحًا.", parse_mode="HTML")
                return
        else:
            mute_duration = None
    
    # تطبيق الكتم
    if mute_duration:
        until_date = int(time.time()) + mute_duration * 60
        bot.restrict_chat_member(chat_id, target_id, until_date=until_date, can_send_messages=False)
        bot.reply_to(message, f"تم تقييد العضو {target_username or target_id} من الكتابة لمدة {mute_duration} دقيقة\n"
                              f"⏳ بعد انتهاء الوقت سيعود إلى إزعاجنا", parse_mode="HTML")
    else:
        bot.restrict_chat_member(chat_id, target_id, can_send_messages=False)
        bot.reply_to(message, f"تم تقييد العضو {target_username or target_id} بشكل دائم.", parse_mode="HTML")
        
              
@bot.message_handler(commands=['unmute'])
def unmute_user(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_user_admin(bot, chat_id, user_id):
        bot.reply_to(message, "**عذرًا!**\nهذا الأمر مخصص للمشرفين فقط.\nلا تقم بذلك مرة أخرى، هذا أمر خطير", parse_mode="Markdown")
        return
    target_id, target_username = extract_user_info(bot, message)
    if not target_id:
        bot.reply_to(message, "**كيفية استخدام الأمر:**\n"
                              "1. بالرد على رسالة العضو: `/unmute`\n"
                              "2. باستخدام الأيدي: `/unmute 12345`\n", parse_mode="Markdown")
        return
    try:
        bot.restrict_chat_member(chat_id, target_id, can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True)
        bot.reply_to(message, f"**تم إلغاء تقييد العضو** [{target_username}](tg://user?id={target_id}).\n"
                              f"🎉 الآن يمكنه التحدث بحرية مرة أخرى!", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"حدث خطأ أثناء محاولة إلغاء تقييد العضو: {e}")
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    users.add(user_id)  
    if not is_user_subscribed(user_id):
        markup = types.InlineKeyboardMarkup()
        subscribe_button = types.InlineKeyboardButton("اشترك الآن", url=CHANNEL_URL)
        check_button = types.InlineKeyboardButton("تحقق من الاشتراك", callback_data="check_subscription")
        markup.add(subscribe_button, check_button)
        bot.send_message(
            message.chat.id,
            "⚠️ يجب عليك الاشتراك في القناة أولاً لاستخدام البوت:\n\n"
            f"👉 {CHANNEL_URL}",
            reply_markup=markup
        )
        return
    notification_message = (
        f"<b>📢 مستخدم جديد بدأ استخدام البوت!</b>\n\n"
        f"<b>👤 الاسم:</b> {message.from_user.first_name}\n"
        f"<b>📎 اليوزر:</b> @{message.from_user.username or 'بدون'}\n"
        f"<b>🆔 الآيدي:</b> {user_id}"
    )
    bot.send_message(DEVELOPER_CHAT_ID, notification_message, parse_mode="HTML")
    welcome_message = (
    "<b>👋 أهلاً بك في بوت الحماية المتطور!</b>\n\n"
    "<b>📢 لتفعيل البوت أضفني إلى مجموعتك وارفعني مشرفًا وسأعمل تلقائيا 🔄</b>\n"
    "<b>🔥 سأقوم بحماية مجموعتك من المحتوى غير الملائم والميديا الغير أخلاقية.</b>\n"
    "<b>❗️ عليك أيضًا إضافة البوت المساعد @Masaeeddbot لتفعيل جميع الوظائف خاصة فحص جميع أنواع الميديا بشكل كامل وأيضا أستطيع حظر المزعجين وتقيدهم أيضا</b>"
)  
    markup = types.InlineKeyboardMarkup()
    button_add_group = types.InlineKeyboardButton("➕ أضفني إلى مجموعتك", url=f"https://t.me/{bot.get_me().username}?startgroup=true")
    button_channel = types.InlineKeyboardButton("📢 قناة المطور", url=CHANNEL_URL)
    markup.add(button_add_group, button_channel)
    bot.send_message(message.chat.id, welcome_message, parse_mode="HTML", reply_markup=markup)
@bot.callback_query_handler(func=lambda call: call.data == "check_subscription")
def check_subscription(call):
    """التعامل مع زر التحقق من الاشتراك"""
    user_id = call.from_user.id
    if is_user_subscribed(user_id):
        bot.answer_callback_query(call.id, "✅ أنت مشترك في القناة! يمكنك الآن استخدام البوت.")
        start(call.message)
    else:
        bot.answer_callback_query(call.id, "❌ لم يتم الاشتراك بعد. يرجى الاشتراك في القناة أولاً.")
@bot.message_handler(content_types=['left_chat_member'])
def handle_manual_ban(message):
    chat_id = message.chat.id
    if chat_id in activated_groups:
        user = message.left_chat_member
        event = f"تم طرد العضو يدويًا: @{user.username if user.username else user.id}"
        daily_reports[chat_id]["manual_actions"].append(event)        
        
        
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    """التعامل مع الصور المرسلة والتحقق من محتواها"""
    file_id = message.photo[-1].file_id
    file_info = bot.get_file(file_id)   
    file_link = f'https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}'
    res = check_image_safety(file_link)
    if res == 'nude':
        bot.delete_message(message.chat.id, message.message_id)
        warning_message = (
            f"🚫 <b>لا ترسل صور غير لائقة يا {message.from_user.first_name}!</b>\n"
            f"🫵 @{message.from_user.username or str(message.from_user.id)}، <b>هذا تنبيه لك!</b>\n"
            "<b>🤖 البوت يراقب ويمنع المحتوى غير الملائم 🛂</b>"
        )
        bot.send_message(message.chat.id, warning_message, parse_mode="HTML")
        update_violations(message.from_user.id, message.chat.id)
@bot.message_handler(content_types=['sticker'])
def handle_sticker(message):
    """التعامل مع الملصقات المرسلة والتحقق من محتواها"""
    if message.sticker.thumb:
        file_info = bot.get_file(message.sticker.thumb.file_id)
        sticker_url = f'https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}'
        res = check_image_safety(sticker_url)
        if res == 'nude':
            bot.delete_message(message.chat.id, message.message_id)
            warning_message = (
                f"🚫 <b>لا ترسل ملصقات غير لائقة يا {message.from_user.first_name}!</b>\n"
                f"🫵 @{message.from_user.username or str(message.from_user.id)}، <b>هذا تنبيه لك!</b>\n"
                "<b>🤖 البوت يراقب ويمنع المحتوى غير الملائم 🛂</b>"
            )
            bot.send_message(message.chat.id, warning_message, parse_mode="HTML")
            update_violations(message.from_user.id, message.chat.id)
@bot.message_handler(func=lambda message: message.entities and any(entity.type == 'custom_emoji' for entity in message.entities))
def handle_custom_emoji_message(message):
    """التعامل مع الرموز التعبيرية الخاصة والتحقق من محتواها"""
    custom_emoji_ids = [entity.custom_emoji_id for entity in message.entities if entity.type == 'custom_emoji']
    if custom_emoji_ids:
        sticker_links = get_premium_sticker_info(custom_emoji_ids)  
        if sticker_links:
            for link in sticker_links:
                res = check_image_safety(link)
                if res == 'nude':
                    bot.delete_message(message.chat.id, message.message_id)
                    warning_message = (
                        f"🚫 <b>لا ترسل رموز غير لائقة يا {message.from_user.first_name}!</b>\n"
                        f"🫵 @{message.from_user.username or str(message.from_user.id)}، <b>هذا تنبيه لك!</b>\n"
                        "<b>🤖 البوت يراقب ويمنع المحتوى غير الملائم 🛂</b>"
                    )
                    bot.send_message(message.chat.id, warning_message, parse_mode="HTML")
                    update_violations(message.from_user.id, message.chat.id)
def get_premium_sticker_info(custom_emoji_ids):
    """استخراج الروابط الخاصة بالرموز التعبيرية"""
    try:
        sticker_set = bot.get_custom_emoji_stickers(custom_emoji_ids)
        sticker_links = []
        for sticker in sticker_set:
            if sticker.thumb:
                file_info = bot.get_file(sticker.thumb.file_id)
                file_link = f'https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}'
                sticker_links.append(file_link)
        return sticker_links
    except Exception as e:
        print(f"Error retrieving sticker info: {e}")
        return []
@bot.edited_message_handler(content_types=['text'])
def handle_edited_custom_emoji_message(message):
    """التعامل مع الرسائل المعدلة وفحص الرموز التعبيرية المميزة"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_name = f"@{message.from_user.username}" if message.from_user.username else f"({user_id})"

    if message.entities:
        custom_emoji_ids = [entity.custom_emoji_id for entity in message.entities if entity.type == 'custom_emoji']
        if custom_emoji_ids:
            sticker_links = get_premium_sticker_info(custom_emoji_ids)
            if sticker_links:
                for link in sticker_links:
                    res = check_image_safety(link)
                    if res == 'nude':
                        bot.delete_message(chat_id, message.message_id)
                        alert_message = (
                            f"🚨 <b>تنبيه:</b>\n"
                            f"🔗 المستخدم {user_name} <b>عدل رسالة وأضاف رمز تعبيري غير لائق!</b>\n\n"
                            "⚠️ <b>يجب على المشرفين اتخاذ الإجراءات اللازمة.</b>"
                        )
                        bot.send_message(chat_id, alert_message, parse_mode="HTML")
                        update_violations(user_id, chat_id)        
        
@bot.edited_message_handler(content_types=['text', 'photo', 'sticker'])
def handle_edited_message(message):
    """التعامل مع الرسائل المعدلة وفحص محتواها"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_name = f"@{message.from_user.username}" if message.from_user.username else f"({user_id})"

    # فحص الصور المعدلة
    if message.content_type == 'photo':  
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        file_link = f'https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}'
        res = check_image_safety(file_link)    

        if res == 'nude':  
            bot.delete_message(chat_id, message.message_id)
            alert_message = (
                f"🚨 <b>تنبيه:</b>\n"
                f"🔗 المستخدم {user_name} <b>حاول تعديل رسالة قديمة إلى صورة غير لائقة!</b>\n\n"
                "⚠️ <b>وجب على المشرفين التعامل معه فورًا بحظره أو تحذيره.</b>"
            )
            bot.send_message(chat_id, alert_message, parse_mode="HTML")
            update_violations(user_id, chat_id)

    # فحص الملصقات المعدلة
    elif message.content_type == 'sticker': 
        if message.sticker.thumb:  
            file_info = bot.get_file(message.sticker.thumb.file_id)
            sticker_url = f'https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}'
            res = check_image_safety(sticker_url)    

            if res == 'nude':  
                bot.delete_message(chat_id, message.message_id)
                alert_message = (
                    f"🚨 <b>تنبيه:</b>\n"
                    f"🔗 المستخدم {user_name} <b>حاول تعديل رسالة قديمة إلى ملصق غير لائق!</b>\n\n"
                    "⚠️ <b>وجب على المشرفين التعامل معه فورًا بحظره أو تحذيره.</b>"
                )
                bot.send_message(chat_id, alert_message, parse_mode="HTML")
                update_violations(user_id, chat_id)


def update_violations(user_id, chat_id):
    global user_violations

    # زيادة عدد مخالفات المستخدم
    if user_id not in user_violations:
        user_violations[user_id] = 0
    user_violations[user_id] += 1

    # جلب معلومات المستخدم
    try:
        chat_member = bot.get_chat_member(chat_id, user_id)
        user = chat_member.user
        user_name = user.first_name or "غير معروف"
        user_username = f"@{user.username}" if user.username else "لا يوجد"
        user_id_text = f"<code>{user_id}</code>"  # لجعل الآيدي يظهر بشكل واضح
        violation_count = user_violations[user_id]

        # تقرير المخالفة
        violation_report = (
            f"🚨 <b>تنبيه بمخالفة جديدة!</b>\n\n"
            f"👤 <b>الاسم:</b> {user_name}\n"
            f"📎 <b>اليوزر:</b> {user_username}\n"
            f"🆔 <b>الآيدي:</b> {user_id_text}\n"
            f"🔢 <b>عدد المخالفات:</b> {violation_count}"
        )

        # إرسال التقرير إلى المجموعة المفعلة إذا كانت التقارير مفعلة
        if chat_id in activated_groups:
            report_chat_id = activated_groups[chat_id]
            daily_reports[chat_id]["deleted_content"].append(violation_report)
            bot.send_message(report_chat_id, violation_report, parse_mode="HTML")

    except Exception as e:
        print(f"❌ خطأ أثناء جلب معلومات المستخدم: {e}")
        return

    # تقييد المستخدم تلقائيًا إذا تجاوز 10 مخالفات (باستثناء المشرفين)
    if violation_count >= 10:
        try:
            if chat_member.status in ['administrator', 'creator']:
                warning_message = (
                    f"🚨 <b>تحذير!</b>\n"
                    f"👤 <b>المستخدم:</b> {user_name}\n"
                    f"📎 <b>اليوزر:</b> {user_username}\n"
                    f"🆔 <b>الآيدي:</b> {user_id_text}\n"
                    f"⚠️ <b>قام بارتكاب مخالفات كثيرة، لكنه مشرف ولا يمكن تقييده.</b>\n"
                    "⚠️ <b>يرجى التعامل معه يدويًا.</b>"
                )
                bot.send_message(chat_id, warning_message, parse_mode="HTML")
            else:
                bot.restrict_chat_member(chat_id, user_id, until_date=None, can_send_messages=False)
                restriction_message = (
                    f"🚫 <b>تم تقييد المستخدم بسبب تجاوز الحد المسموح به من المخالفات!</b>\n\n"
                    f"👤 <b>الاسم:</b> {user_name}\n"
                    f"📎 <b>اليوزر:</b> {user_username}\n"
                    f"🆔 <b>الآيدي:</b> {user_id_text}\n"
                    f"🔢 <b>عدد المخالفات:</b> {violation_count}\n\n"
                    "⚠️ <b>تم تقييده تلقائيًا.</b>"
                )
                bot.send_message(chat_id, restriction_message, parse_mode="HTML")

        except Exception as e:
            print(f"❌ خطأ أثناء محاولة تقييد المستخدم: {e}")
@bot.message_handler(content_types=['new_chat_members'])
def on_user_joins(message):
    """التعامل مع انضمام أعضاء جدد للمجموعة"""
    for member in message.new_chat_members:
        groups.add(message.chat.id) 
        added_by = message.from_user
        try:
            if bot.get_chat_member(message.chat.id, added_by.id).can_invite_users:
                group_link = bot.export_chat_invite_link(message.chat.id)
                welcome_message = (
                    f"🤖 <b>تم إضافة البوت بواسطة:</b>\n"
                    f"👤 <b>الاسم:</b> {added_by.first_name}\n"
                    f"📎 <b>اليوزر:</b> @{added_by.username or 'بدون'}\n"
                    f"🆔 <b>الآيدي:</b> {added_by.id}\n"
                )                
                if group_link:
                    welcome_message += f"\n🔗 <b>رابط الدعوة للمجموعة:</b> {group_link}"
                bot.send_message(message.chat.id, welcome_message, parse_mode="HTML")
        except Exception as e:
            print(f"Error while exporting chat invite link: {e}")
def broadcast_message(message_text):
    for user_id in users:
        try:
            bot.send_message(user_id, message_text)
        except Exception as e:
            print(f"Error sending message to user {user_id}: {e}")    
    for group_id in groups:
        try:
            bot.send_message(group_id, message_text)
        except Exception as e:
            print(f"Error sending message to group {group_id}: {e}")
@bot.message_handler(commands=['broadcast'])
def handle_broadcast(message):
    """إرسال رسالة جماعية للمستخدمين والمجموعات"""
    if str(message.chat.id) == DEVELOPER_CHAT_ID:
        msg_text = message.text.split(maxsplit=1)
        if len(msg_text) > 1:
            broadcast_message(msg_text[1])
            bot.send_message(message.chat.id, "📢 تم إرسال الرسالة بنجاح إلى جميع المستخدمين والمجموعات!")
        else:
            bot.send_message(message.chat.id, "🚫 يرجى كتابة الرسالة بعد الأمر /broadcast.")
    else:
        bot.send_message(message.chat.id, "🚫 هذا الأمر مخصص للمطور فقط.")
@bot.message_handler(commands=['sb'])
def handle_sb_command(message):
    """رد خاص للمطور عند إرسال أمر /sb"""
    if str(message.from_user.id) == DEVELOPER_CHAT_ID:
        bot.reply_to(message, "نعم عزيزي المطور البوت يعمل بنجاح 💪")
    else:
        bot.reply_to(message, "🚫 هذا الأمر مخصص للمطور فقط.")
@bot.message_handler(commands=['id'])
def send_chat_id(message):
    """عرض ID للمجموعة فقط"""
    try:
        chat_info = bot.get_chat(message.chat.id)  # الحصول على معلومات الدردشة
        if chat_info.type in ['group', 'supergroup']:  # التحقق إذا كانت مجموعة
            bot.reply_to(message, f"Group ID: {message.chat.id}\nاضغط لنسخ المعرف: {message.chat.id}")
        else:
            bot.reply_to(message, "🚫 هذا الأمر مخصص للمجموعات فقط!")
    except Exception as e:
        bot.reply_to(message, f"🚫 حدث خطأ: {str(e)}")

def schedule_daily_report(group_id):
    """جدولة إرسال التقرير اليومي تلقائيًا كل 24 ساعة"""
    def send_report():
        send_group_report(group_id)  # إرسال التقرير
        threading.Timer(86400, send_report).start()  # إعادة التشغيل بعد 24 ساعة
    
    threading.Timer(86400, send_report).start()

@bot.message_handler(commands=['report'])
def manual_daily_report(message):
    """عرض التقرير اليومي عند الطلب"""
    chat_id = message.chat.id
    user_id = message.from_user.id

    # التحقق مما إذا كان المستخدم مشرفًا
    if not is_user_admin(bot, chat_id, user_id):
        bot.reply_to(message, "❌ هذا الأمر متاح للمشرفين فقط.")
        return

    # إرسال التقرير يدويًا
    send_group_report(chat_id)

def send_group_report(group_id):
    """تجميع وإرسال التقرير للمجموعة"""
    if group_id in daily_reports and any(daily_reports[group_id].values()):  # التأكد أن هناك بيانات
        report = daily_reports[group_id]
        report_chat_id = activated_groups.get(group_id, group_id)  # تحديد مجموعة الإشعارات أو نفس المجموعة

        msg = "📅 **التقرير اليومي**\n\n"
        msg += f"🔨 الأعضاء المحظورين:\n" + ("\n".join(report["banned"]) if report["banned"] else "لا يوجد") + "\n\n"
        msg += f"🔇 الأعضاء المكتمين:\n" + ("\n".join(report["muted"]) if report["muted"] else "لا يوجد") + "\n\n"
        msg += f"🚮 المحتوى المحذوف:\n" + ("\n".join(report["deleted_content"]) if report["deleted_content"] else "لا يوجد") + "\n\n"
        msg += f"👥 الإجراءات اليدوية:\n" + ("\n".join(report["manual_actions"]) if report["manual_actions"] else "لا يوجد")

        bot.send_message(report_chat_id, msg, parse_mode="Markdown")

    else:
        bot.send_message(group_id, "📢 لا يوجد سجل للمخالفات اليوم.", parse_mode="Markdown")

def reset_daily_reports():
    """إعادة تصفير السجلات كل 24 ساعة"""
    global daily_reports
    daily_reports = {group_id: {"banned": [], "muted": [], "deleted_content": [], "manual_actions": []} for group_id in activated_groups}
    print("✅ تم إعادة تصفير السجلات اليومية.")
    threading.Timer(86400, reset_daily_reports).start()  # إعادة التصغير بعد 24 ساعة

# تشغيل تصفير السجلات لأول مرة
reset_daily_reports()
        
commands = [
    telebot.types.BotCommand("ban", "حظر عضو (بالرد، الأيدي، أو اليوزرنيم)"),
    telebot.types.BotCommand("unban", "إلغاء حظر عضو (بالرد، الأيدي، أو اليوزرنيم)"),
    telebot.types.BotCommand("mute", "تقييد عضو من الكتابة (بالرد، الأيدي، أو اليوزرنيم)"),
    telebot.types.BotCommand("unmute", "إلغاء تقييد عضو (بالرد، الأيدي، أو اليوزرنيم)"),
     telebot.types.BotCommand("opengbt", "للمشرف فقط (تفعيل الذكاء بلمجموعة)"),
      telebot.types.BotCommand("closegbt", "للمشرف فقط (تعطيل الذكاء بلمجموعة)"),
       telebot.types.BotCommand("gbt", "الذكاء الأصطناعي gbt-4 (ارسل رسالتك للذكاء مع الأمر)"),
telebot.types.BotCommand("enable_reports", "تفعيل إرسال التقارير اليومية لمجموعتك"),
           
]
bot.set_my_commands(commands)
try:
    print("🚀 البوت يعمل الآن بنجاح!")
    bot.infinity_polling()
except Exception as e:
    print(f"🚫 حدث خطأ: {e}")
