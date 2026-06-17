import telebot
import requests
import json
import markdown
from bs4 import BeautifulSoup
import os
import tempfile
import re # لاستخدام التعبيرات النمطية

# توكن البوت اللي حصلته من BotFather
# من الأفضل تخزينه كمتغير بيئة (Environment Variable) لأمان أفضل
# لكن للتبسيط، راح نخليه هنا. تأكد من تغييره!
API_TOKEN = '8732016265:AAFyPyHnsFuXQbeBUfe9neD-pXg-IVD7xlU'

bot = telebot.TeleBot(API_TOKEN)

# دالة تحويل HTML إلى Telegra.ph Nodes
def html_to_node(element):
    if isinstance(element, str):
        return element
    
    node = {"tag": element.name}
    
    if element.attrs:
        # Telegra.ph API لا يدعم كل خصائص HTML، نركز على المهمة مثل href للروابط
        # ونضيف دعم لـ dir للتحكم باتجاه النص (RTL/LTR)
        supported_attrs = {}
        if 'href' in element.attrs: supported_attrs['href'] = element.attrs['href']
        if 'src' in element.attrs: supported_attrs['src'] = element.attrs['src']
        if 'class' in element.attrs: supported_attrs['class'] = element.attrs['class']
        if 'dir' in element.attrs: supported_attrs['dir'] = element.attrs['dir'] # إضافة دعم لاتجاه النص
        if supported_attrs: node["attrs"] = supported_attrs
        
    children = []
    for child in element.children:
        if child.name is None:
            if str(child).strip():
                children.append(str(child))
        else:
            children.append(html_to_node(child))
            
    if children:
        node["children"] = children
        
    return node

# دالة نشر المحتوى على Telegra.ph
def publish_to_telegraph(title, markdown_content):
    try:
        # تحويل Markdown إلى HTML
        # يمكن إضافة extensions لـ markdown لتحسين الدعم لبعض التنسيقات
        html_content = markdown.markdown(markdown_content, extensions=['fenced_code', 'tables', 'nl2br'])
        
        # تحليل HTML إلى Telegra.ph nodes
        soup = BeautifulSoup(html_content, "html.parser")
        nodes = []
        for element in soup.children:
            if element.name is not None:
                nodes.append(html_to_node(element))
                
        # إنشاء حساب Telegra.ph مؤقت (يمكن إعادة استخدام access_token إذا تم حفظه)
        create_account_url = "https://api.telegra.ph/createAccount"
        account_data = {
            "short_name": "MdToTgBot", 
            "author_name": "Markdown to Telegraph Bot"
        }
        response = requests.post(create_account_url, data=account_data)
        response.raise_for_status() 
        access_token = response.json()["result"]["access_token"]
        
        # إنشاء صفحة Telegra.ph
        create_page_url = "https://api.telegra.ph/createPage"
        page_data = {
            "access_token": access_token,
            "title": title,
            "content": json.dumps(nodes),
            "return_content": "true"
        }
        response = requests.post(create_page_url, data=page_data)
        response.raise_for_status() 
        
        if response.json()["ok"]:
            return response.json()["result"]["url"]
        else:
            return f"خطأ في Telegra.ph API: {response.json()["error"]}"
            
    except requests.exceptions.RequestException as e:
        return f"خطأ في الاتصال بـ Telegra.ph: {e}"
    except json.JSONDecodeError:
        return "خطأ في تحليل رد Telegra.ph API."
    except Exception as e:
        return f"حدث خطأ غير متوقع: {e}"

# معالج الأمر /start
@bot.message_handler(commands=["start"])
def send_welcome(message):
    bot.reply_to(message, "أهلاً بك! أنا بوت يحول ملفات Markdown إلى صفحات Telegra.ph. فقط أرسل لي ملف Markdown (.md) وسأقوم بنشره لك فوراً.")

# معالج ملفات المستندات
@bot.message_handler(content_types=["document"])
def handle_document(message):
    if message.document.file_name.endswith(".md"):
        bot.reply_to(message, "جاري معالجة ملف Markdown الخاص بك...")
        
        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            with tempfile.NamedTemporaryFile(mode='w+', delete=False, encoding='utf-8', suffix='.md') as temp_md_file:
                temp_md_file.write(downloaded_file.decode('utf-8'))
                temp_md_file_path = temp_md_file.name
            
            with open(temp_md_file_path, 'r', encoding='utf-8') as f:
                markdown_content = f.read()
            
            # توليد عنوان للصفحة (تحسين معالجة العنوان)
            title = os.path.splitext(message.document.file_name)[0]
            if not title: 
                title = "صفحة Markdown من البوت"
            
            # إزالة الشرطات السفلية واستبدالها بمسافات من العنوان
            title = title.replace('_', ' ')
            # إزالة أي رموز غير مرغوبة أو مسافات زائدة من العنوان
            title = re.sub(r'[^\w\s]', '', title) # إزالة الرموز ما عدا الأحرف والأرقام والمسافات
            title = re.sub(r'\s+', ' ', title).strip() # استبدال المسافات المتعددة بمسافة واحدة وحذف المسافات من الأطراف

            # نشر المحتوى على Telegra.ph
            telegraph_url = publish_to_telegraph(title, markdown_content)
            
            if telegraph_url.startswith("http"):
                bot.reply_to(message, f"تم نشر صفحتك بنجاح! الرابط: {telegraph_url}")
            else:
                bot.reply_to(message, f"عذراً، حدث خطأ أثناء النشر: {telegraph_url}")
                
        except Exception as e:
            bot.reply_to(message, f"عذراً، حدث خطأ أثناء معالجة ملفك: {e}")
        finally:
            if 'temp_md_file_path' in locals() and os.path.exists(temp_md_file_path):
                os.remove(temp_md_file_path)
                
    else:
        bot.reply_to(message, "عذراً، أنا أستقبل فقط ملفات Markdown (.md).")

# بدء تشغيل البوت
print("البوت قيد التشغيل...")
bot.polling(none_stop=True)
