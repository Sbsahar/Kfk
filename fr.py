import time
import requests
import os
import telebot
import moviepy.editor as mp
from PIL import Image
import tempfile
import json

# إعدادات البوت
TOKEN = '7942028086:AAEwq8CaFeYSSXtSuBWwCCQ3BDtaaX3BZhI'
api_key = "sk_817daf19a4a711cafe9cc6b2d26c18a1efde2d1552e8f2be0b5adc252c6c6222cc2341a0fc70b7a1c56284ec831e282742f72f0c25f8fbcccf687eb90218723b02479KIlfgLXJHcsnuoO1"
GROUP_CHAT_ID = '-1002091669531'
DEVELOPER_ID = 6789179634

bot = telebot.TeleBot(TOKEN)
user_violations = {}  # لتسجيل عدد المخالفات

def is_user_admin(chat_id, user_id):
    """التحقق من صلاحية المشرف"""
    try:
        admins = bot.get_chat_administrators(chat_id)
        return any(admin.user.id == user_id for admin in admins)
    except Exception as e:
        print(f"خطأ في التحقق من الصلاحيات: {e}")
        return False

def update_violations(user_id, chat_id):
    """تحديث عدد المخالفات وتطبيق العقوبات"""
    try:
        # زيادة عدد المخالفات
        user_violations[user_id] = user_violations.get(user_id, 0) + 1
        
        # إذا وصلت المخالفات إلى 10
        if user_violations[user_id] >= 10:
            if is_user_admin(chat_id, user_id):
                bot.send_message(
                    chat_id,
                    f"🚨 المشرف {get_user_mention(user_id)} تجاوز 10 مخالفات!",
                    parse_mode="HTML"
                )
                return
            
            # تقييد المستخدم لمدة 24 ساعة
            bot.restrict_chat_member(
                chat_id,
                user_id,
                until_date=int(time.time()) + 86400,
                can_send_messages=False
            )
            
            # إرسال إشعار للمجموعة
            bot.send_message(
                chat_id,
                f"🚫 تم تقييد العضو {get_user_mention(user_id)}\n"
                "❌ السبب: تجاوز عدد المخالفات المسموح بها (10 مرات)\n"
                "⏳ المدة: 24 ساعة",
                parse_mode="HTML"
            )
            
            # إعادة تعيين العداد
            user_violations[user_id] = 0
            
    except Exception as e:
        print(f"خطأ في تحديث المخالفات: {e}")

def get_user_mention(user_id):
    """الحصول على mention للمستخدم"""
    try:
        user = bot.get_chat(user_id)
        return f'<a href="tg://user?id={user.id}">{user.first_name}</a>'
    except:
        return f"المستخدم ({user_id})"

def check_image_safety(image_path):
    """فحص سلامة الصورة"""
    api_url = "https://api.jigsawstack.com/v1/validate/nsfw"
    headers = {"x-api-key": api_key}
    
    try:
        with open(image_path, 'rb') as img_file:
            sent_image = bot.send_photo(GROUP_CHAT_ID, img_file)
            image_url = f'https://api.telegram.org/file/bot{TOKEN}/{bot.get_file(sent_image.photo[-1].file_id).file_path}'
            
            time.sleep(1)
            response = requests.get(api_url, headers=headers, params={"url": image_url})
            
            if response.status_code == 200:
                result = response.json()
                bot.delete_message(GROUP_CHAT_ID, sent_image.message_id)
                return 'nude' if result.get('nudity', False) else 'ok'
            return 'error'
    except Exception as e:
        print(f"خطأ في فحص الصورة: {e}")
        return 'error'

def process_media(content, file_extension, message, media_type):
    """معالجة الميديا واستخراج الإطارات"""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
            temp_file.write(content)
            temp_file.close()
            
            # استخراج الإطارات
            clip = mp.VideoFileClip(temp_file.name)
            frames = [
                Image.fromarray(clip.get_frame(t))
                for t in [i * 2 for i in range(3)]  # 5 إطارات كل ثانيتين
            ]
            
            # فحص كل إطار
            for frame in frames:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as frame_file:
                    frame.save(frame_file, format='JPEG')
                    frame_file.close()
                    
                    if check_image_safety(frame_file.name) == 'nude':
                        handle_violation(message, media_type)
                        os.unlink(frame_file.name)
                        break
                    
                    os.unlink(frame_file.name)
            
            os.unlink(temp_file.name)
    except Exception as e:
        print(f"خطأ في معالجة الميديا: {e}")

def handle_violation(message, content_type):
    """معالجة المخالفة"""
    try:
        # حذف الرسالة الأصلية
        bot.delete_message(message.chat.id, message.message_id)
        
        # إرسال التحذير
        warning_msg = (
            f"⚠️ <b>تنبيه!</b>\n"
            f"العضو: {get_user_mention(message.from_user.id)}\n"
            f"نوع المخالفة: {content_type} غير لائق\n"
            f"عدد المخالفات: {user_violations.get(message.from_user.id, 0)+1}/10"
        )
        bot.send_message(message.chat.id, warning_msg, parse_mode="HTML")
        
        # تحديث عدد المخالفات
        update_violations(message.from_user.id, message.chat.id)
        
    except Exception as e:
        print(f"خطأ في معالجة المخالفة: {e}")

@bot.message_handler(content_types=['animation'])
def handle_gif(message):
    """معالجة ملفات GIF"""
    try:
        file_info = bot.get_file(message.animation.file_id)
        file_url = f'https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}'
        response = requests.get(file_url)
        
        if response.status_code == 200:
            process_media(response.content, '.gif', message, 'صورة متحركة')
    except Exception as e:
        print(f"خطأ في معالجة GIF: {e}")

@bot.message_handler(content_types=['video'])
def handle_video(message):
    """معالجة الفيديوهات"""
    try:
        file_info = bot.get_file(message.video.file_id)
        file_url = f'https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}'
        response = requests.get(file_url)
        
        if response.status_code == 200:
            process_media(response.content, '.mp4', message, 'فيديو')
    except Exception as e:
        print(f"خطأ في معالجة الفيديو: {e}")

@bot.edited_message_handler(content_types=['animation', 'video'])
def handle_edited_media(message):
    """معالجة الميديا المعدلة"""
    if message.animation:
        handle_gif(message)
    elif message.video:
        handle_video(message)

@bot.message_handler
@bot.message_handler(commands=['sb'])
def developer_check(message):
    """فحص حالة البوت للمطور"""
    if message.from_user.id == DEVELOPER_ID:
        bot.reply_to(message, "✅ البوت يعمل بشكل طبيعي")
    else:
        bot.delete_message(message.chat.id, message.message_id)

# تشغيل البوت
while True:
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"حدث خطأ: {e}")
        time.sleep(15)
