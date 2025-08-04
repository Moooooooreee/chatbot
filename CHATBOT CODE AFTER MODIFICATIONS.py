import telebot
import os
import cv2
import numpy as np
import pandas as pd
# import time
import json
from pyzbar.pyzbar import decode
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
TOKEN = '7812784214:AAG3GLhlxcXR_7YeOrwKnI-MjuPOoKMB-Ws'
bot = telebot.TeleBot(TOKEN)

Visits = "imei_data.xlsx"
Database = "database.xlsx"
PASSWORD = "123"
AUTH_FILE = "authenticated_users.json"

try:
    with open(AUTH_FILE, 'r') as f:
        authenticated_users = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    authenticated_users = {}

user_states = {}

def save_authenticated_users():
    with open(AUTH_FILE, 'w') as f:
        json.dump(authenticated_users, f)

@bot.message_handler(commands=['start'])
def start(message):
    chat_id = str(message.chat.id)
    if chat_id in authenticated_users:
        bot.reply_to(
            message,
            "مرحباً.\n"
            "يرجى ارسال صورة لرقم الجهاز أو ادخاله يدوياً"
        )
    else:
        user_states[chat_id]={"state":"awaiting_password"}
        bot.reply_to(
            message,
            "مرحباً، يرجى إدخال كود التعريف للاستمرار:"
        )

# Command to contact support
@bot.message_handler(commands=['support'])
def support(message):
    df = pd.read_excel(Visits, dtype={"IMEI": str, "Work done": str})
    imei = user_states.get(str(message.chat.id), {}).get("IMEI")
    df.loc[(df["IMEI"] == imei), "Status"] = "Support"
    df.to_excel(Visits, index=False)

    bot.reply_to(
        message,
        "اذا واجهت مشكله برجاء ارسال على جروب ال WhatsApp."
    )

# handle entering password then a phone number
@bot.message_handler(func=lambda message: str(message.chat.id) not in authenticated_users)
def handle_auth_steps(message):
    chat_id = str(message.chat.id)

    if chat_id not in user_states:
        user_states[chat_id] = {"state": "awaiting_password"}

    current_state = user_states[chat_id].get("state", "awaiting_password")

    if current_state == "awaiting_password":
        if message.text == PASSWORD:
        
            user_states.setdefault(chat_id, {}).update({
                "state": "awaiting_phone",
                "name": f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
            })



            
            bot.reply_to(
                message,
                "كود التعريف صحيح.\n\n"
                "الرجاء إدخال رقم هاتفك:"
            )
        else:
            bot.reply_to(
                message,
                "كود التعريف غير صحيح. يرجى المحاولة مجدداً."
            )

    elif current_state == "awaiting_phone":
        phone = ''.join(filter(str.isdigit, message.text))
        if 10 <= len(phone) <= 15:
            authenticated_users[chat_id] = {
                "authenticated": True,
                "name": user_states[chat_id]["name"],
                "phone": phone,
                "timestamp": datetime.now().strftime("%d %b %Y, %I:%M %p")
            }
            save_authenticated_users()

            bot.reply_to(
                message,
                f"شكراً ، {user_states[chat_id]['name']}!\n"
                "يرجى ارسال صورة لرقم الجهاز أو ادخاله يدوياً"
            )
            user_states.pop(chat_id, None)
        else:
            bot.reply_to(
                message,
                "رقم الهاتف غير صالح. يرجى إدخال رقم صحيح مكون من 10 الى 15 رقم."
            )

# handle getting the imei (only if authenticated)
@bot.message_handler(content_types=['photo', 'text'], func=lambda message: str(message.chat.id) in authenticated_users)
def handle_imei(message):
    try:
        chat_id = str(message.chat.id)
        imei = None
        if message.content_type == 'photo':
            # Get the file ID and download the image
            file_id = message.photo[-1].file_id
            file_info = bot.get_file(file_id)
            downloaded_file = bot.download_file(file_info.file_path)

            # convert img to suitable format for openCV
            img = np.asarray(bytearray(downloaded_file), dtype=np.uint8)
            img = cv2.imdecode(img, cv2.IMREAD_COLOR)

            decoded_objects = decode(img)
            if decoded_objects:
                imei = decoded_objects[0].data.decode('utf-8')

                os.makedirs("imei_images", exist_ok=True)  #save img by its imei
                cv2.imwrite(f"imei_images/{imei}.jpg", img)

        elif message.content_type == 'text':
            imei = ''.join(filter(str.isdigit, message.text)).lstrip('0')

            if len(imei) != 15:
                bot.reply_to(
                    message,
                    " يجب أن يحتوي IMEI على 15 رقماً\n"
                    f"الأرقام المدخلة: {imei}\n"
                    "الرجاء المحاولة مجدداً"
                )
                return

        if imei:
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("نعم", callback_data="confirm_yes"),
                InlineKeyboardButton("لا", callback_data="confirm_no")
            )
   
            
            user_states.setdefault(chat_id, {}).update({"IMEI": imei})


            bot.send_message(message.chat.id, f"رقم الجهاز: {imei}\n\nهل هذا الرقم صحيح؟", reply_markup=markup)
        else:
            bot.reply_to(message, "رقم الجهاز غير واضح\n من فضلك ارسال صوره اكثر وضوحا ")
    except Exception as e:
        bot.reply_to(message, f"An error occurred: {str(e)}")

# handle inline button presses for confirmation
@bot.callback_query_handler(func=lambda call: call.data in ["confirm_yes", "confirm_no"])
def handle_confirmation(call):
    chat_id = str(call.message.chat.id)
    user_entry = user_states.get(chat_id, {})
    tech_name = f"{call.from_user.first_name} {call.from_user.last_name or ''}".strip()

    if call.data == "confirm_yes":
        imei = user_entry.get("IMEI")
        if imei:
            try:
                date = datetime.now().strftime("%Y-%m-%d %H:%M")
                df = pd.read_excel(Visits, dtype={"IMEI": str, "Work done": str})

     
                if not ((df["Visit date"] == date) & (df["IMEI"] == imei)).any():
                    df = pd.concat([df, pd.DataFrame({
                        "Date": [date],
                        "IMEI": [imei],
                        "Note": [""],
                        "Status": ["Incomplete"],
                        "R": [np.nan],
                        "gap": [np.nan],
                        "Technician": [tech_name]
                    })], ignore_index=True)


                # repeat = 1 # flag to recheck again
                activation_msg = False # flag for activation msg
                wg_msg_sent = False
                # while True: #repeat == 1:
                with open(Database, "rb") as f:
                    df2 = pd.read_excel(f, dtype={"IMEI": str}).copy()

                imei_row = df2.loc[df2["IMEI"] == imei]

                if not imei_row.empty:
                    status = imei_row["status"].values[0]
                else:
                    df2 = pd.concat([df2, pd.DataFrame({"IMEI": [imei], "status": ["inactive"],"airgap":[0],"src":[0],"rssi":[0]})], ignore_index=True) # remove on deploying
                    df2.to_excel(Database, index=False)

                    # df.loc[(df["Visit date"] == date) & (df["IMEI"] == imei), "Work done"] = "New Device" #remove
                    bot.send_message(chat_id, "New device,\nIMEI added to the database.")
                    status = "inactive"

                if status == "inactive": 
                    if activation_msg == False:
                        bot.send_message(chat_id, f"Status: {status}")
                        bot.send_message(chat_id, f"ارسل هذه الرساله مره واحده فقط \nو شغل الجهاز مرتين")
                        bot.send_message(chat_id, f"3&x!yz,R3=ACTIVE")
                        done_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("تم", callback_data="activated")]])
                        bot.send_message(chat_id, "اضغط \"تم\" بعد الانطفاءه الاخرى للجهاز", reply_markup=done_keyboard)
                        df.loc[(df["Visit date"] == date) & (df["IMEI"] == imei), "Work done"] = "Activation msg"
                        activation_msg = True

                elif status == "active":
                    airgap = imei_row["airgap"].values[0]
                    src = imei_row["src"].values[0]
                    rssi = imei_row["rssi"].values[0]
                    battery = imei_row["battery"].values[0]

                    if battery < 5:
                            bot.send_message(chat_id, f" مستوى البطارية منخفض: {battery} v.\nيرجى تغيير البطارية قبل المتابعة.")
                            # need confirmation that he has changed it or not available
                            # if so, check again if > 5 else, wp group
                            # save in excel wethear it has changed in "Work done" or need to be replaced in "Notes" or changed but still < 5 in "Problem"

                    bot.send_message(chat_id, f"القراءات:\nاجمالى الفراغ: {airgap}سم\nSRC: {src}\nRSSI: {rssi}")

                    if src == 10 and rssi == 10:
                        bot.send_message(chat_id, "كم ارتفاع الجهاز عن الخزان؟")
                        bot.register_next_step_handler(call.message, get_r, airgap, src, rssi, date, imei)

                    elif src <10 and rssi >=9 and wg_msg_sent == False:
                        bot.send_message(chat_id, "3&x!yz,S17=0014FF3C3C")
                        bot.send_message(chat_id, "Send this msg then")
                        bot.send_message(chat_id, "يرجى إعادة تشغيل الجهاز مرتين من الان.")

                        # need to adjuste new handler for the folllowing
                        # it should check on the status of the command if =false then ask to wake the device again if true then back to the logic again
                        done_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("تم", callback_data="waveguide")]])
                        bot.send_message(chat_id, "اضغط \"تم\" بعد الانطفاءه الاخرى للجهاز", reply_markup=done_keyboard)
                        wg_msg_sent = True

                    elif src>=9 and rssi<10:
                        recheck_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("إعادة التحقق", callback_data="recheck")]])
                        bot.send_message(chat_id, f"نظف العدسه و اعد التحقق من فضلك", reply_markup=recheck_keyboard)

                    else: # the uncovered cases where both<10 || src<10 && rssi==10 && wg_msg_sent =True
                        recheck_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("إعادة التحقق", callback_data="recheck")]])
                        bot.send_message(chat_id, f"برجاء مراجعه التثبيت و التشغيل مره اخرى", reply_markup=recheck_keyboard)
                        # bot.send_message(chat_id, f"اتبع خطوات الصيانه الاتيه:\n1- نظف العدسه و القاعده\n2- قم بتغير البطاريات\n3- تأكد ان فتحه الخزان ليست اصغر من القاعده و الا سوف تحتاج للتوسيع\n\n ينصح بتركيب انبوب دائما لتجنب ضعف القراءات", reply_markup=recheck_keyboard) #remove

                        # if activation_msg == False:
                        #     df.loc[(df["Visit date"] == date) & (df["IMEI"] == imei), "Work done"] = "Maintenance"
                        # repeat = 0  # exit the loop ##meeret
                        # break
                    # 3ayz a3mel flag f ay recheck 3shan don't save again fel excel
                # else: # New Device
                #     # df2 = pd.read_excel(Database, dtype={"IMEI": str, "status": str}) #remove
                #     df2 = pd.concat([df2, pd.DataFrame({"IMEI": [imei], "status": ["inactive"],"airgap":[0],"src":[0],"rssi":[0]})], ignore_index=True) # remove on deploying
                #     df2.to_excel(Database, index=False)

                #     # df.loc[(df["Visit date"] == date) & (df["IMEI"] == imei), "Work done"] = "New Device" #remove
                #     bot.send_message(chat_id, "New device,\nIMEI added to the database.")
                #     time.sleep(3) #  wait 5 mins(3000 sec) till recheck
                #     # repeat = 0  # exit the loop ##

                df.to_excel(Visits, index=False)

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
        df = pd.read_excel(Visits, dtype={"IMEI": str, "Work done": str})
        if abs(airgap - (r + gap)) <= 1:
            bot.send_message(message.chat.id, f"شكرا, القراءات ممتازه تفضل")
            df.loc[(df["Visit date"] == date) & (df["IMEI"] == imei), "Status"] = "Fixed"

            mask = (df["Visit date"] == date) & (df["IMEI"] == imei)
            df.loc[mask, "Work done"] = df.loc[mask, "Work done"].fillna("").apply(lambda x: f"{x}, Waveguide installed" if x else "Waveguide installed")

        else:
            bot.send_message(message.chat.id, f"برجاء مراجعه القياسات \nالاجمالى: {airgap} سم\n\n\nكم ارتفاع الجهاز عن الخزان؟")
            bot.register_next_step_handler(message, get_r, airgap, src, rssi, date, imei)

        # Save Raiser and Gap to Excel in the same row
        df.loc[(df["Visit date"] == date) & (df["IMEI"] == imei), ["Raiser", "Gap"]] = [r, gap]
        df.to_excel(Visits, index=False)
    except ValueError:
        bot.send_message(message.chat.id, "برجاء إدخال رقم صحيح.")
        bot.register_next_step_handler(message, get_gap, airgap, src, rssi, r, date, imei)

@bot.callback_query_handler(func=lambda call: call.data == "recheck")
def handle_recheck(call):
    chat_id = call.message.chat.id
    bot.send_message(chat_id, "جارٍ إعادة التحقق من القراءات...")
    handle_confirmation(call)

@bot.callback_query_handler(func=lambda call: call.data == "activated")
def handle_activated(call):
    chat_id = str(call.message.chat.id)
    imei = user_states.get(chat_id, {}).get("IMEI")

    status = pd.read_excel(Database, dtype={"IMEI": str}) \
                .loc[lambda df: df["IMEI"] == imei, "status"].values[0]

    if status == "active":
        handle_confirmation(call)
    else:
        bot.send_message(call.message.chat.id, "لم يتم التفعيل بعد، يرجى الضغط مرة أخرى بعد تشغيل الجهاز مجددا.")

print("Bot is running...")
bot.infinity_polling()
