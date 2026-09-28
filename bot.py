import asyncio
import sys

# Force event loop creation for Python 3.14+ compatibility
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

import os
import logging
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery, InputMediaPhoto
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, FloodWait
from pyrogram.raw.functions.messages import GetDialogs
from pyrogram.raw.functions.account import UpdateProfile
from pyrogram.raw.types import InputPeerEmpty
from motor.motor_asyncio import AsyncIOMotorClient

# Enable logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- Configuration & Environment Variables ---
API_ID = int(os.environ.get("API_ID", "123456"))
API_HASH = os.environ.get("API_HASH", "your_api_hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_bot_token")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true&w=majority")

# Fixed Admin ID (1936430807)
PRIMARY_ADMIN_ID = 1936430807

PORT = int(os.environ.get("PORT", "8080"))

# Initialize Flask for Render Uptime Robot Keep-Alive
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "Ads Manager Bot is running smoothly!"

def run_flask():
    app_flask.run(host="0.0.0.0", port=PORT)

# Initialize Bot Client
bot = Client("ads_manager_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Initialize Database
mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client["ads_manager_database"]
users_col = db["users"]
accounts_col = db["accounts"]
ads_col = db["ads"]
settings_col = db["settings"]
forcesub_col = db["forcesub"]
admins_col = db["admins"]

# Active running tasks dictionary
active_workers = {}
temp_sessions = {}
admin_states = {}

# Default Dashboard Image (Agar Database me na mile to)
DEFAULT_DASHBOARD_PIC = "https://telegra.ph/file/0b93892809e072d627c54.jpg"

# --- Helper Functions ---
async def is_admin(user_id: int):
    if user_id == PRIMARY_ADMIN_ID:
        return True
    admin = await admins_col.find_one({"user_id": user_id})
    return bool(admin)

async def check_forcesub(client, user_id):
    try:
        channels = await forcesub_col.find().to_list(length=100)
        if not channels:
            return []
        
        not_joined = []
        for ch in channels:
            ch_id = ch["channel"]
            try:
                member = await client.get_chat_member(ch_id, user_id)
                if member.status in ["left", "kicked"]:
                    not_joined.append(ch_id)
            except Exception:
                pass
                
        return not_joined
    except Exception:
        return []

async def get_dashboard_pic():
    config = await settings_col.find_one({"type": "bot_config"})
    if config and config.get("dashboard_pic"):
        return config["dashboard_pic"]
    return DEFAULT_DASHBOARD_PIC

# --- /start Command & Main Dashboard ---
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message: Message):
    user_id = message.from_user.id
    
    user_exists = await users_col.find_one({"user_id": user_id})
    if not user_exists:
        await users_col.insert_one({"user_id": user_id, "joined_date": message.date, "bio_set": False})
        
    not_joined = await check_forcesub(client, user_id)
    if not_joined and not await is_admin(user_id):
        buttons = []
        for ch in not_joined:
            clean_ch = ch.replace('@','').replace('-100','')
            buttons.append([InlineKeyboardButton("Join Channel", url=f"https://t.me/{clean_ch}")])
        buttons.append([InlineKeyboardButton("🔄 Try Again", callback_data="check_forcesub")])
        await message.reply("⚠️ **Please join our update channels first to use this bot!**", reply_markup=InlineKeyboardMarkup(buttons))
        return

    await show_dashboard(message)

async def show_dashboard(message_or_query, edit=False):
    if isinstance(message_or_query, CallbackQuery):
        user_id = message_or_query.from_user.id
        msg = message_or_query.message
    else:
        user_id = message_or_query.from_user.id
        msg = message_or_query

    acc_count = await accounts_col.count_documents({"user_id": user_id})
    ad_data = await ads_col.find_one({"user_id": user_id})
    settings = await settings_col.find_one({"user_id": user_id}) or {"interval": 5, "ad_status": "Stopped ⛔", "auto_reply": False}
    
    service_status = "Set ✅" if ad_data else "Not set ❌"
    ad_status = settings.get("ad_status", "Stopped ⛔")
    interval = settings.get("interval", 5)
    dash_pic = await get_dashboard_pic()

    text = (
        "─── **Powered by @adsmanage13_bot** ───\n\n"
        f"• **Hosted Accounts:** `{acc_count}/20`\n"
        f"• **Service:** `{service_status}`\n"
        f"• **Advertisement status:** `{ad_status}`\n"
        f"• **Interval:** `{interval} minutes`\n"
        f"• **Current plan:** `Free`"
    )

    btn_layout = [
        [InlineKeyboardButton("👤 Manage Accounts", callback_data="manage_accounts"), InlineKeyboardButton("📢 Set Advertisement", callback_data="set_ad")],
        [InlineKeyboardButton("⏰ Interval & Delay", callback_data="set_interval"), InlineKeyboardButton("▶️ Run Ads", callback_data="run_ads")],
        [InlineKeyboardButton("⏹ Stop Ads", callback_data="stop_ads"), InlineKeyboardButton("🤖 Auto Reply", callback_data="auto_reply")],
        [InlineKeyboardButton("ℹ️ About Bot", callback_data="about_bot")]
    ]

    if await is_admin(user_id):
        btn_layout.append([InlineKeyboardButton("👑 Admin Panel", callback_data="open_admin_panel")])

    keyboard = InlineKeyboardMarkup(btn_layout)

    if edit:
        try:
            await msg.edit_media(
                media=InputMediaPhoto(media=dash_pic, caption=text),
                reply_markup=keyboard
            )
        except Exception:
            await msg.edit_text(text, reply_markup=keyboard)
    else:
        try:
            await msg.reply_photo(photo=dash_pic, caption=text, reply_markup=keyboard)
        except Exception:
            await msg.reply(text, reply_markup=keyboard)

@bot.on_callback_query(filters.regex("check_forcesub"))
async def check_forcesub_cb(client, callback: CallbackQuery):
    not_joined = await check_forcesub(client, callback.from_user.id)
    if not_joined:
        await callback.answer("❌ You still haven't joined all required channels!", show_alert=True)
    else:
        await callback.answer("✅ Verified successfully!")
        await show_dashboard(callback, edit=True)

# --- Manage & Remove Accounts Flow ---
@bot.on_callback_query(filters.regex("manage_accounts"))
async def manage_accounts_cb(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    accounts = await accounts_col.find({"user_id": user_id}).to_list(length=20)
    
    if not accounts:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Account", callback_data="add_account")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_home")]
        ])
        await callback.message.edit_caption(caption="📋 **Your Accounts:**\n\nYou haven't added any Telegram accounts yet.", reply_markup=keyboard)
        return

    keyboard_buttons = []
    for acc in accounts:
        keyboard_buttons.append([InlineKeyboardButton(f"📱 {acc['phone']} (❌ Remove)", callback_data=f"rem_acc_{acc['phone']}")])
    
    keyboard_buttons.append([InlineKeyboardButton("➕ Add Another Account", callback_data="add_account")])
    keyboard_buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_home")])
    
    await callback.message.edit_caption(caption="📋 **Your Hosted Accounts:**\nClick on any account below to remove it:", reply_markup=InlineKeyboardMarkup(keyboard_buttons))

@bot.on_callback_query(filters.regex(r"^rem_acc_"))
async def remove_account_cb(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    phone = callback.data.replace("rem_acc_", "")
    
    await accounts_col.delete_one({"user_id": user_id, "phone": phone})
    
    if user_id in active_workers:
        active_workers[user_id].cancel()
        del active_workers[user_id]
        await settings_col.update_one({"user_id": user_id}, {"$set": {"ad_status": "Stopped ⛔"}}, upsert=True)
        
    await callback.answer(f"✅ Account {phone} removed successfully!", show_alert=True)
    await manage_accounts_cb(client, callback)

@bot.on_callback_query(filters.regex("add_account"))
async def add_account_cb(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    acc_count = await accounts_col.count_documents({"user_id": user_id})
    if acc_count >= 20:
        await callback.answer("⚠️ Maximum account limit (20) reached!", show_alert=True)
        return
    temp_sessions[user_id] = {"step": "waiting_phone"}
    await callback.message.reply("Send your phone number with country code.\nExample: `+919876543210`")

# Unified Text Message Router
@bot.on_message(filters.private & (filters.text | filters.photo))
async def unified_text_handler(client, message: Message):
    user_id = message.from_user.id
    
    if user_id in admin_states:
        state = admin_states[user_id]
        del admin_states[user_id]
        
        if state == "wait_dash_pic":
            pic_media = None
            if message.photo:
                pic_media = message.photo.file_id
            elif message.text:
                pic_media = message.text.strip()
            
            if pic_media:
                await settings_col.update_one({"type": "bot_config"}, {"$set": {"dashboard_pic": pic_media}}, upsert=True)
                await message.reply("✅ **Dashboard Photo Updated Successfully!**")
            else:
                await message.reply("❌ Invalid input! Send a photo or an image URL.")
            return

        elif state == "wait_add_admin":
            try:
                new_admin_id = int(message.text.strip())
                await admins_col.update_one({"user_id": new_admin_id}, {"$set": {"user_id": new_admin_id}}, upsert=True)
                await message.reply("✅ Admin added successfully!")
            except Exception as e:
                await message.reply(f"❌ Error: {e}")
            return
        elif state == "wait_rem_admin":
            try:
                rem_id = int(message.text.strip())
                await admins_col.delete_one({"user_id": rem_id})
                await message.reply("✅ Admin removed successfully!")
            except Exception as e:
                await message.reply(f"❌ Error: {e}")
            return
        elif state == "wait_add_fsub":
            ch = message.text.strip()
            await forcesub_col.update_one({"channel": ch}, {"$set": {"channel": ch}}, upsert=True)
            await message.reply("✅ Force Sub channel added successfully!")
            return
        elif state == "wait_rem_fsub":
            ch = message.text.strip()
            await forcesub_col.delete_one({"channel": ch})
            await message.reply("✅ Force Sub channel removed successfully!")
            return
        elif state == "wait_broadcast":
            bc_text = message.text
            users = await users_col.find().to_list(length=50000)
            success, failed = 0, 0
            status_msg = await message.reply("Broadcast Started...")
            for u in users:
                try:
                    await client.send_message(u["user_id"], bc_text)
                    success += 1
                    await asyncio.sleep(0.1)
                except:
                    failed += 1
            await status_msg.edit_text(f"✅ **Broadcast Completed!**\n\nSuccess: `{success}`\nFailed: `{failed}`")
            return

    if user_id not in temp_sessions:
        return
    
    state = temp_sessions[user_id]
    
    if state["step"] == "waiting_phone":
        phone = message.text.strip()
        state["phone"] = phone
        try:
            userbot = Client(f"temp_session_{user_id}", api_id=API_ID, api_hash=API_HASH, in_memory=True)
            await userbot.connect()
            sent_code = await userbot.send_code(phone)
            state["userbot"] = userbot
            state["phone_code_hash"] = sent_code.phone_code_hash
            state["step"] = "waiting_otp"
            await message.reply("OTP has been sent to your Telegram account.\n\nEnter OTP (e.g. 1 2 3 4 5):")
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}\nTry again /start")
            del temp_sessions[user_id]
            
    elif state["step"] == "waiting_otp":
        otp = message.text.strip().replace(" ", "")
        userbot = state["userbot"]
        phone = state["phone"]
        hash_code = state["phone_code_hash"]
        
        try:
            await userbot.sign_in(phone, hash_code, otp)
            session_string = await userbot.export_session_string()
            await accounts_col.insert_one({"user_id": user_id, "phone": phone, "session_string": session_string})
            await userbot.disconnect()
            del temp_sessions[user_id]
            await message.reply("✅ Account Added Successfully!")
            await show_dashboard(message)
        except SessionPasswordNeeded:
            state["step"] = "waiting_password"
            await message.reply("Two-Step Verification detected.\n\nEnter your password:")
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}\nStart over with /start")
            del temp_sessions[user_id]

    elif state["step"] == "waiting_password":
        password = message.text.strip()
        userbot = state["userbot"]
        try:
            await userbot.check_password(password)
            session_string = await userbot.export_session_string()
            await accounts_col.insert_one({"user_id": user_id, "phone": state["phone"], "session_string": session_string})
            await userbot.disconnect()
            del temp_sessions[user_id]
            await message.reply("✅ Account Added Successfully with 2FA!")
            await show_dashboard(message)
        except Exception as e:
            await message.reply(f"❌ Password Error: {str(e)}\nStart over with /start")
            del temp_sessions[user_id]

    elif state["step"] == "waiting_ad_text":
        ad_text = message.text
        await ads_col.update_one({"user_id": user_id}, {"$set": {"text": ad_text}}, upsert=True)
        del temp_sessions[user_id]
        await message.reply("✅ Advertisement Saved Successfully!")
        await show_dashboard(message)

    elif state["step"] == "waiting_autoreply_text":
        ar_text = message.text
        await settings_col.update_one({"user_id": user_id}, {"$set": {"auto_reply_text": ar_text, "auto_reply": True}}, upsert=True)
        del temp_sessions[user_id]
        await message.reply("✅ Auto Reply Enabled & Message Saved!")
        await show_dashboard(message)

# --- Set Advertisement ---
@bot.on_callback_query(filters.regex("set_ad"))
async def set_ad_cb(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    temp_sessions[user_id] = {"step": "waiting_ad_text"}
    await callback.message.reply("Send advertisement text:")

# --- Interval & Delay ---
@bot.on_callback_query(filters.regex("set_interval"))
async def set_interval_cb(client, callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("5 Minutes", callback_data="int_5"), InlineKeyboardButton("8 Minutes", callback_data="int_8")],
        [InlineKeyboardButton("10 Minutes", callback_data="int_10"), InlineKeyboardButton("15 Minutes", callback_data="int_15")],
        [InlineKeyboardButton("30 Minutes", callback_data="int_30")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_home")]
    ])
    await callback.message.edit_caption(caption="Select Advertisement Interval:", reply_markup=keyboard)

@bot.on_callback_query(filters.regex(r"^int_"))
async def save_interval_cb(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    interval = int(callback.data.split("_")[1])
    await settings_col.update_one({"user_id": user_id}, {"$set": {"interval": interval}}, upsert=True)
    await callback.answer("✅ Interval Updated!")
    await show_dashboard(callback, edit=True)

# --- Auto Reply Menu ---
@bot.on_callback_query(filters.regex("auto_reply"))
async def auto_reply_menu(client, callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Enable 🟢", callback_data="ar_enable"), InlineKeyboardButton("Disable 🔴", callback_data="ar_disable")],
        [InlineKeyboardButton("Edit Message 📝", callback_data="ar_edit")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_home")]
    ])
    await callback.message.edit_caption(caption="🤖 **Auto Reply Settings**\nConfigure automated response for incoming direct messages on your userbots.", reply_markup=keyboard)

@bot.on_callback_query(filters.regex("ar_enable"))
async def ar_enable_cb(client, callback: CallbackQuery):
    await settings_col.update_one({"user_id": callback.from_user.id}, {"$set": {"auto_reply": True}}, upsert=True)
    await callback.answer("✅ Auto Reply Enabled")
    await show_dashboard(callback, edit=True)

@bot.on_callback_query(filters.regex("ar_disable"))
async def ar_disable_cb(client, callback: CallbackQuery):
    await settings_col.update_one({"user_id": callback.from_user.id}, {"$set": {"auto_reply": False}}, upsert=True)
    await callback.answer("❌ Auto Reply Disabled")
    await show_dashboard(callback, edit=True)

@bot.on_callback_query(filters.regex("ar_edit"))
async def ar_edit_cb(client, callback: CallbackQuery):
    temp_sessions[callback.from_user.id] = {"step": "waiting_autoreply_text"}
    await callback.message.reply("Send your auto-reply message text:")

# --- Run & Stop Ads Worker ---
async def ad_worker(bot_client, user_id):
    log_msg = None
    try:
        logger.info(f"Ad worker started for user {user_id}")
        log_msg = await bot_client.send_message(user_id, "🚀 **Ad Worker Initialized!**")
        account = await accounts_col.find_one({"user_id": user_id})
        ad = await ads_col.find_one({"user_id": user_id})
        
        if not account or not ad:
            if log_msg:
                await log_msg.edit_text("❌ **Error:** Account or Advertisement text missing!")
            return
            
        userbot = Client(f"worker_{user_id}", session_string=account["session_string"], api_id=API_ID, api_hash=API_HASH, in_memory=True)
        await userbot.start()

        # Check if bio is already updated for first time
        user_db_data = await users_col.find_one({"user_id": user_id})
        if user_db_data and not user_db_data.get("bio_set", False):
            try:
                await userbot.invoke(UpdateProfile(about="Free Auto ads via @adsmanage13_bot"))
                await users_col.update_one({"user_id": user_id}, {"$set": {"bio_set": True}})
            except Exception as bio_err:
                logger.error(f"Bio set error: {bio_err}")

        discovered_groups = set()

        @userbot.on_message(filters.group)
        async def live_group_harvester(client, message):
            if message.chat:
                discovered_groups.add((message.chat.id, message.chat.title or "Unnamed Group"))

        while True:
            settings = await settings_col.find_one({"user_id": user_id})
            if not settings or settings.get("ad_status") != "Running 🚀":
                if log_msg:
                    await log_msg.edit_text("⛔ **Ad Campaign Stopped.**")
                break
                
            sent_count, failed_count = 0, 0
            fetched_groups_info = ""
            chat_ids_to_target = set()
            
            try:
                r = await userbot.invoke(GetDialogs(offset_date=0, offset_id=0, offset_peer=InputPeerEmpty(), limit=500, hash=0))
                for chat in r.chats:
                    if hasattr(chat, "title") and (chat.__class__.__name__ in ["Chat", "Channel"]):
                        if chat.__class__.__name__ == "Channel":
                            if getattr(chat, "megagroup", False):
                                chat_ids_to_target.add((int(f"-100{chat.id}"), chat.title))
                        else:
                            chat_ids_to_target.add((int(f"-{chat.id}"), chat.title))
            except Exception as raw_err:
                logger.error(f"Raw MTProto error: {raw_err}")

            for g_id, g_title in discovered_groups:
                chat_ids_to_target.add((g_id, g_title))

            dialog_count = len(chat_ids_to_target)

            if dialog_count == 0:
                if log_msg:
                    await log_msg.edit_text("⏳ **Listening for active group chats...**")
                await asyncio.sleep(20)
                continue

            for chat_id, chat_title in chat_ids_to_target:
                try:
                    await userbot.send_message(chat_id, ad["text"])
                    sent_count += 1
                    fetched_groups_info += f"\n• {chat_title} ➔ Sent ✅"
                    await asyncio.sleep(3)
                except FloodWait as fw:
                    await asyncio.sleep(fw.value)
                    try:
                        await userbot.send_message(chat_id, ad["text"])
                        sent_count += 1
                        fetched_groups_info += f"\n• {chat_title} ➔ Sent ✅"
                    except:
                        failed_count += 1
                        fetched_groups_info += f"\n• {chat_title} ➔ Failed ❌"
                except Exception:
                    failed_count += 1
                    fetched_groups_info += f"\n• {chat_title} ➔ Failed ❌"
            
            summary_text = (
                f"📊 **Ad Cycle Report:**\n\n"
                f"• Total Groups Found: `{dialog_count}`\n"
                f"• Successfully Sent: `{sent_count}`\n"
                f"• Failed / Restricted: `{failed_count}`\n\n"
                f"📋 **Groups Status Details:**\n"
                f"{fetched_groups_info[:3000]}"
            )
            
            if log_msg:
                try:
                    await log_msg.edit_text(summary_text)
                except Exception:
                    pass
            
            interval_mins = settings.get("interval", 5)
            await asyncio.sleep(interval_mins * 60)
            
        await userbot.stop()
    except Exception as e:
        logger.error(f"Worker Error: {e}")

@bot.on_callback_query(filters.regex("run_ads"))
async def run_ads_cb(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    ad = await ads_col.find_one({"user_id": user_id})
    acc = await accounts_col.find_one({"user_id": user_id})
    
    if not ad or not acc:
        await callback.answer("⚠️ Set ad & account first!", show_alert=True)
        return
        
    await settings_col.update_one({"user_id": user_id}, {"$set": {"ad_status": "Running 🚀"}}, upsert=True)
    if user_id in active_workers:
        active_workers[user_id].cancel()

    task = asyncio.create_task(ad_worker(client, user_id))
    active_workers[user_id] = task
    await callback.answer("🚀 Started!")
    await show_dashboard(callback, edit=True)

@bot.on_callback_query(filters.regex("stop_ads"))
async def stop_ads_cb(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    await settings_col.update_one({"user_id": user_id}, {"$set": {"ad_status": "Stopped ⛔"}}, upsert=True)
    if user_id in active_workers:
        active_workers[user_id].cancel()
        del active_workers[user_id]
    await callback.answer("⛔ Stopped!")
    await show_dashboard(callback, edit=True)

@bot.on_callback_query(filters.regex("about_bot"))
async def about_cb(client, callback: CallbackQuery):
    await callback.message.edit_caption(caption="ℹ️ **Ads Manager Bot**\nPowered by Pyrogram.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_home")]]))

@bot.on_callback_query(filters.regex("back_home"))
async def back_home_cb(client, callback: CallbackQuery):
    await show_dashboard(callback, edit=True)

# --- Admin Panel ---
@bot.on_callback_query(filters.regex("^open_admin_panel$"))
async def open_admin_panel_cb(client, callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Unauthorized!", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🖼 Set Dashboard Photo", callback_data="adm_set_pic")],
        [InlineKeyboardButton("👑 Add Admin", callback_data="adm_add"), InlineKeyboardButton("❌ Remove Admin", callback_data="adm_rem")],
        [InlineKeyboardButton("📋 Admin List", callback_data="adm_list"), InlineKeyboardButton("🔒 Add Force Sub", callback_data="fsub_add")],
        [InlineKeyboardButton("🔓 Remove Force Sub", callback_data="fsub_rem"), InlineKeyboardButton("📋 Force Sub List", callback_data="fsub_list")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="adm_bc"), InlineKeyboardButton("📊 Statistics", callback_data="adm_stats")],
        [InlineKeyboardButton("🔙 Back to Dashboard", callback_data="back_home")]
    ])
    await callback.message.edit_caption(caption="👑 **Admin Control Panel**", reply_markup=keyboard)

@bot.on_callback_query(filters.regex(r"^(adm_|fsub_|back_admin)"))
async def admin_buttons_cb(client, callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Unauthorized!", show_alert=True)
        return
        
    data = callback.data
    user_id = callback.from_user.id
    
    if data == "adm_set_pic":
        admin_states[user_id] = "wait_dash_pic"
        await callback.message.reply("Send photo OR direct photo URL to set as dashboard image:")
    elif data == "adm_add":
        admin_states[user_id] = "wait_add_admin"
        await callback.message.reply("Send the Telegram User ID of the new admin:")
    elif data == "adm_rem":
        admin_states[user_id] = "wait_rem_admin"
        await callback.message.reply("Send the Telegram User ID of the admin to remove:")
    elif data == "adm_list":
        admins = await admins_col.find().to_list(length=100)
        text = f"📋 **Admin List:**\nPrimary Admin: `{PRIMARY_ADMIN_ID}`\n"
        for a in admins:
            text += f"- `{a['user_id']}`\n"
        await callback.message.edit_caption(caption=text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="open_admin_panel")]]))
    elif data == "fsub_add":
        admin_states[user_id] = "wait_add_fsub"
        await callback.message.reply("Send channel username or private ID (`@channel` or `-100xxx`):")
    elif data == "fsub_rem":
        admin_states[user_id] = "wait_rem_fsub"
        await callback.message.reply("Send channel username or ID to remove:")
    elif data == "fsub_list":
        subs = await forcesub_col.find().to_list(length=100)
        text = "📋 **Force Sub Channels:**\n"
        for s in subs:
            text += f"- `{s['channel']}`\n"
        await callback.message.edit_caption(caption=text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="open_admin_panel")]]))
    elif data == "adm_bc":
        admin_states[user_id] = "wait_broadcast"
        await callback.message.reply("Send the broadcast message:")
    elif data == "adm_stats":
        total_users = await users_col.count_documents({})
        total_accs = await accounts_col.count_documents({})
        text = f"📊 **Bot Statistics:**\n\nTotal Users: `{total_users}`\nHosted Accounts: `{total_accs}`"
        await callback.message.edit_caption(caption=text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="open_admin_panel")]]))

# --- Main Entry Point ---
if __name__ == "__main__":
    import threading
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    print("Bot is starting...")
    bot.run()
