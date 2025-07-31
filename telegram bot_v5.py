import telebot
import cv2
import numpy as np
import pandas as pd
import time
from pyzbar.pyzbar import decode
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from openpyxl import load_workbook

TOKEN = '7812784214:AAG3GLhlxcXR_7YeOrwKnI-MjuPOoKMB-Ws'
bot = telebot.TeleBot(TOKEN)

EXCEL_FILE = "imei_data.xlsx"
EXCEL_FILE_2 = "database.xlsx"

# Ensure the Excel file exists with necessary sheets
df1 = pd.read_excel(EXCEL_FILE, sheet_name=0, dtype={"IMEI": str, "Note": str})

# Dictionary to track user state and extracted IMEI
user_data = {}

# Command to start the bot
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(
        message,
        "مرحبا, يرجى ارسال صوره لرقم الجهاز"
    )

# Handle photo messages
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    try:
        # Get the file ID and download the image
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Convert the image to a format suitable for OpenCV
        img = np.asarray(bytearray(downloaded_file), dtype=np.uint8)
        img = cv2.imdecode(img, cv2.IMREAD_COLOR)
        
        # Process the image to find barcodes
        decoded_objects = decode(img)
        if decoded_objects:
            for obj in decoded_objects:
                barcode_data = obj.data.decode('utf-8')
                user_data[message.chat.id] = {"IMEI": barcode_data}
                
                # Create inline buttons for confirmation
                markup = InlineKeyboardMarkup()
                markup.add(
                    InlineKeyboardButton("نعم", callback_data="confirm_yes"),
                    InlineKeyboardButton("لا", callback_data="confirm_no")
                )
                bot.send_message(message.chat.id, f"رقم الجهاز: {barcode_data}\n\nهل هذا الرقم صحيح؟", reply_markup=markup)
                return
        else:
            bot.reply_to(message, "من فضلك ارسال صوره اكثر وضوحا")
    except Exception as e:
        bot.reply_to(message, f"An error occurred: {str(e)}")

# Handle inline button presses for confirmation
@bot.callback_query_handler(func=lambda call: call.data in ["confirm_yes", "confirm_no"])
def handle_confirmation(call):
    chat_id = call.message.chat.id
    user_entry = user_data.get(chat_id, {})
    if call.data == "confirm_yes":
        imei = user_entry.get("IMEI")
        if imei:
            try:
                date = datetime.now().strftime("%Y-%m-%d %H:%M")
                df = pd.read_excel(EXCEL_FILE, dtype={"IMEI": str, "Note": str})
                df = pd.concat([df, pd.DataFrame({"Date": [date], "IMEI": [imei], "Note": [""], "R": [np.nan], "gap": [np.nan]})], ignore_index=True)
                
                repeat = 1 # flag to recheck again          
                activation_msg = 0 # flag for activation msg
                while repeat == 1:
                    df2 = pd.read_excel(EXCEL_FILE_2, dtype={"IMEI": str})
                    imei_row = df2.loc[df2["IMEI"] == imei]
                                    
                    if not imei_row.empty:
                        status = imei_row["status"].values[0]                  
                        
                        if status == "inactive":
                            if activation_msg == 0:
                                bot.send_message(chat_id, f"Status: {status}")
                                bot.send_message(chat_id, f"ارسل هذه الرساله مره واحده فقط \nو شغل الجهاز مرتين")
                                bot.send_message(chat_id, f"3&x!yz,R3=ACTIVE")
                                done_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("تم", callback_data="activated")]])
                                bot.send_message(chat_id, "اضغط \"تم\" بعد الانطفاءه الاخرى للجهاز", reply_markup=done_keyboard)
                                activation_msg = 1
                            
                            @bot.callback_query_handler(func=lambda call: True) # should not define handler inside another one
                            def callback_query(call):
                                df2 = pd.read_excel(EXCEL_FILE_2, dtype={"IMEI": str})

                                if call.data == "activated":
                                    bot.send_message(call.message.chat.id, "لم يتم التفعيل بعد,\n برجاء الانتظار او التشغيل مره اخرى \nثم اضغط على \"تم\" مجددا")
                                    call.data = None
                            break # for debuging df.to_excel
                            
                        elif status == "active":
                            airgap = imei_row["airgap"].values[0]
                            src = imei_row["src"].values[0]
                            rssi = imei_row["rssi"].values[0]
                            bot.send_message(chat_id, f"القراءات:\nAirgap: {airgap}\nSRC: {src}\nRSSI: {rssi}")

                            if src == 10 and rssi == 10:
                                bot.send_message(chat_id, "كم ارتفاع الجهاز عن الخزان؟")
                                bot.register_next_step_handler(call.message, get_r, airgap, src, rssi, date, imei)
                            else:
                                recheck_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("إعادة التحقق", callback_data="recheck")]])
                                if activation_msg == 1:
                                    bot.send_message(chat_id, f"برجاء مراجعه التثبيت و التشغيل مره اخرى", reply_markup=recheck_keyboard)
                                else : # no activation msg, means maintenance
                                    bot.send_message(chat_id, f"اتبع خطوات الصيانه الاتيه\n1- نظف العدسه و القاعده\n2- قم بتغير البطاريات\n3- تأكد من فتحه الخزان ليست اصغر من القاعده و الا سوف تحتاج للتوسيع\n\n ينصح بتركيب انبوب دائما لتجنب مثل تلك المشاكل", reply_markup=recheck_keyboard)
                            break
                       # 3ayz a3mel flag f ay recheck 3shan don't save again fel excel
                    else: # New Device
                        df2 = pd.read_excel(EXCEL_FILE_2, dtype={"IMEI": str, "status": str}) # to be removed
                        df2 = pd.concat([df2, pd.DataFrame({"IMEI": [imei], "status": ["inactive"],"airgap":[0],"src":[0],"rssi":[0]})], ignore_index=True)
                        df2.to_excel(EXCEL_FILE_2, index=False)

                        df.loc[(df['Date'] == date) & (df['IMEI'] == imei), 'Note'] = "New Device"
                        bot.send_message(chat_id, "New device,\nIMEI added to the database.")
                        time.sleep(3) # wait 5 mins(3000 sec) till recheck 
                
                df.to_excel(EXCEL_FILE, index=False)
            
            except Exception as e:
                bot.send_message(chat_id, f"Error reading from database: {str(e)}")

    elif call.data == "confirm_no":
        bot.send_message(chat_id, "من فضلك ارسال صوره اكثر وضوحا")

def get_r(message, airgap, src, rssi, date, imei):
    try:
        r = int(message.text)
        bot.send_message(message.chat.id, "كم نسبه الفارغ؟")
        bot.register_next_step_handler(message, get_gap, airgap, src, rssi, r, date, imei)
    except ValueError:
        bot.send_message(message.chat.id, "برجاء إدخال رقم صحيح.")
        bot.register_next_step_handler(message, get_r, airgap, src, rssi, date, imei)

def get_gap(message, airgap, src, rssi, r, date, imei):
    try:
        gap = int(message.text)
        df = pd.read_excel(EXCEL_FILE, dtype={"IMEI": str, "Note": str})
        if abs(airgap - (r + gap)) <= 1:
            bot.send_message(message.chat.id, f"شكرا, القراءات ممتازه تفضل")
        else:
            bot.send_message(message.chat.id, f"برجاء مراجعه القياسات \nالاجمالى: {airgap} سم\n\n\nكم ارتفاع الجهاز عن الخزان؟")
            bot.register_next_step_handler(message, get_r, airgap, src, rssi, date, imei)
        
        # Save R and gap to Excel in the same row
        df.loc[(df['Date'] == date) & (df['IMEI'] == imei), ['R', 'gap']] = [r, gap]
        df.to_excel(EXCEL_FILE, index=False)
    except ValueError:
        bot.send_message(message.chat.id, "برجاء إدخال رقم صحيح.")
        bot.register_next_step_handler(message, get_gap, airgap, src, rssi, r, date, imei)

@bot.callback_query_handler(func=lambda call: call.data == "recheck")
def handle_recheck(call):
    chat_id = call.message.chat.id
    bot.send_message(chat_id, "جارٍ إعادة التحقق من البيانات...")
    handle_confirmation(call)

print("Bot is running...")
bot.infinity_polling()