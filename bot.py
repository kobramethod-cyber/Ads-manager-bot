Import asyncio
import sys

# Force event loop creation for Python 3.14+ compatibility
try:
    Loop = asyncio.get_event_loop()
except RuntimeError:
    Loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

import os
import logging
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery, InputMediaPhoto
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, FloodWait, RPCError
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

# Initialize Flask for Uptime
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    Return "Ads Manager Bot is running smoothly!"

def run_flask():
    App_flask.run(host="0.0.0.0", port=PORT)

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
welcome_col = db["welcome_msg"]
welcomed_dms_col = db["welcomed_dms"]

# Active running tasks dictionary
active_workers = {}
temp_sessions = {}
admin_states = {}

# Default Values
DEFAULT_DASHBOARD_PIC = "https://telegra.ph/file/0b93892809e072d627c54.jpg"
DEFAULT_DASHBOARD_TEXT = (
    "─── **Powered by @adsmanage13_bot** ───\n\n"
    "• **Hosted Accounts:** `{acc_count}/20`\n"
    "• **Service:** `{service_status}`\n"
    "• **Advertisement status:** `{ad_status}`\n"
    "• **Interval:** `{interval} seconds`\n"
    "• **Current plan:** `Free`"
)

# --- Helper Functions ---
async def is_admin(user_id: int):
    If user_id == PRIMARY_ADMIN_ID:
        Return True
    Admin = await admins_col.find_one({"user_id": user_id})
    Return bool(admin)

async def check_forcesub(client, user_id):
    Try:
        Channels = await forcesub_col.find().to_list(length=100)
        If not channels:
            Return []
        
        Not_joined = []
        For ch in channels:
            Ch_id = ch["channel"]
            Try:
                Member = await client.get_chat_member(ch_id, user_id)
                If member.status in ["left", "kicked"]:
                    Not_joined.append(ch_id)
            Except Exception:
                Pass
                
        Return not_joined
    Except Exception:
        Return []

async def get_dashboard_config():
    Config = await settings_col.find_one({"type": "bot_config"})
    Pic = config.get("dashboard_pic", DEFAULT_DASHBOARD_PIC) if config else DEFAULT_DASHBOARD_PIC
    Text_template = config.get("dashboard_text", DEFAULT_DASHBOARD_TEXT) if config else DEFAULT_DASHBOARD_TEXT
    Return pic, text_template

# --- /start Command & Welcome Feature (Welcome Message Removed for New Users) ---
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message: Message):
    User_id = message.from_user.id
    First_name = message.from_user.first_name or "User"
    Username = message.from_user.username or ""
    
    User_exists = await users_col.find_one({"user_id": user_id})
    
    # Register new user without custom welcome message popup
    If not user_exists:
        await users_col.insert_one({
            "user_id": user_id, 
            "first_name": first_name, 
            "username": username, 
            "joined_date": message.date, 
            "bio_set": False
        })

    # Update info if changed
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": {"first_name": first_name, "username": username}},
        upsert=True
    )

    # Check Force Sub for existing users
    Not_joined = await check_forcesub(client, user_id)
    If not_joined and not await is_admin(user_id):
        Buttons = []
        For ch in not_joined:
            Clean_ch = ch.replace('@','').replace('-100','')
            Buttons.append([InlineKeyboardButton("Join Channel", url=f"https://t.me/{clean_ch}")])
        Buttons.append([InlineKeyboardButton("🔄 Try Again", callback_data="check_forcesub")])
        Await message.reply("⚠️ **Please join our update channels first to use this bot!**", reply_markup=InlineKeyboardMarkup(buttons))
        Return

    Await show_dashboard(message)

# --- Dashboard View ---
async def show_dashboard(message_or_query, edit=False):
    If isinstance(message_or_query, CallbackQuery):
        User_id = message_or_query.from_user.id
        Msg = message_or_query.message
    Else:
        User_id = message_or_query.from_user.id
        Msg = message_or_query

    Acc_count = await accounts_col.count_documents({"user_id": user_id})
    Ad_data = await ads_col.find_one({"user_id": user_id})
    Settings = await settings_col.find_one({"user_id": user_id}) or {"interval": 300, "ad_status": "Stopped ⛔", "auto_reply": False}
    
    Service_status = "Set ✅" if ad_data else "Not set ❌"
    Ad_status = settings.get("ad_status", "Stopped ⛔")
    Interval = settings.get("interval", 300)
    
    Dash_pic, text_template = await get_dashboard_config()

    Try:
        Text = text_template.format(
            Acc_count=acc_count,
            Service_status=service_status,
            Ad_status=ad_status,
            Interval=interval
        )
    Except Exception:
        Text = text_template

    Btn_layout = [
        [InlineKeyboardButton("👤 Manage Accounts", callback_data="manage_accounts"), InlineKeyboardButton("📢 Set Advertisement", callback_data="set_ad")],
        [InlineKeyboardButton("⏰ Interval & Delay", callback_data="set_interval")],
        [InlineKeyboardButton("👋 Set Welcome Message", callback_data="set_welcome")],
        [InlineKeyboardButton("🤖 Auto Reply Settings", callback_data="auto_reply")],
        [InlineKeyboardButton("▶️ Run Ads", callback_data="run_ads"), InlineKeyboardButton("⏹ Stop Ads", callback_data="stop_ads")],
        [InlineKeyboardButton("ℹ️ About Bot", callback_data="about_bot")]
    ]

    If await is_admin(user_id):
        Btn_layout.append([InlineKeyboardButton("👑 Admin Panel", callback_data="open_admin_panel")])

    Keyboard = InlineKeyboardMarkup(btn_layout)

    If edit:
        Try:
            Await msg.edit_media(
                Media=InputMediaPhoto(media=dash_pic, caption=text),
                Reply_markup=keyboard
            )
        Except Exception:
            Await msg.edit_text(text, reply_markup=keyboard)
    Else:
        Try:
            Await msg.reply_photo(photo=dash_pic, caption=text, reply_markup=keyboard)
        Except Exception:
            Await msg.reply(text, reply_markup=keyboard)

@bot.on_callback_query(filters.regex("check_forcesub"))
async def check_forcesub_cb(client, callback: CallbackQuery):
    Not_joined = await check_forcesub(client, callback.from_user.id)
    If not_joined:
        Await callback.answer("❌ You still haven't joined all required channels!", show_alert=True)
    Else:
        Await callback.answer("✅ Verified successfully!")
        Await show_dashboard(callback, edit=True)

# --- Manage Accounts Flow ---
@bot.on_callback_query(filters.regex("manage_accounts"))
async def manage_accounts_cb(client, callback: CallbackQuery):
    User_id = callback.from_user.id
    Accounts = await accounts_col.find({"user_id": user_id}).to_list(length=20)
    
    If not accounts:
        Keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Account", callback_data="add_account")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_home")]
        ])
        Await callback.message.edit_caption(caption="📋 **Your Accounts:**\n\nYou haven't added any Telegram accounts yet.", reply_markup=keyboard)
        Return

    Keyboard_buttons = []
    For acc in accounts:
        Keyboard_buttons.append([InlineKeyboardButton(f"📱 {acc['phone']} (❌ Remove)", callback_data=f"rem_acc_{acc['phone']}")])
    
    Keyboard_buttons.append([InlineKeyboardButton("➕ Add Another Account", callback_data="add_account")])
    Keyboard_buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_home")])
    
    Await callback.message.edit_caption(caption="📋 **Your Hosted Accounts:**\nClick on any account below to remove it:", reply_markup=InlineKeyboardMarkup(keyboard_buttons))

@bot.on_callback_query(filters.regex(r"^rem_acc_"))
async def remove_account_cb(client, callback: CallbackQuery):
    User_id = callback.from_user.id
    Phone = callback.data.replace("rem_acc_", "")
    
    Await accounts_col.delete_one({"user_id": user_id, "phone": phone})
    
    If user_id in active_workers:
        Active_workers[user_id].cancel()
        Del active_workers[user_id]
        Await settings_col.update_one({"user_id": user_id}, {"$set": {"ad_status": "Stopped ⛔"}}, upsert=True)
        
    Await callback.answer(f"✅ Account {phone} removed successfully!", show_alert=True)
    Await manage_accounts_cb(client, callback)

@bot.on_callback_query(filters.regex("add_account"))
async def add_account_cb(client, callback: CallbackQuery):
    User_id = callback.from_user.id
    Acc_count = await accounts_col.count_documents({"user_id": user_id})
    If acc_count >= 20:
        Await callback.answer("⚠️ Maximum account limit (20) reached!", show_alert=True)
        Return
    Temp_sessions[user_id] = {"step": "waiting_phone"}
    Await callback.message.reply("Send your phone number with country code.\nExample: `+919876543210`")

# --- Set Welcome Setup ---
@bot.on_callback_query(filters.regex("set_welcome"))
async def set_welcome_cb(client, callback: CallbackQuery):
    User_id = callback.from_user.id
    Temp_sessions[user_id] = {"step": "waiting_welcome_msg"}
    Instruction = (
        "👋 **Set Custom Welcome Message**\n\n"
        "Send welcome **text**, **photo**, or **video** for your hosted accounts DM.\n\n"
        "💡 **To add a button link, use format:**\n"
        "`Text Message | Button Name | https://yourlink.com`"
    )
    Await callback.message.reply(instruction)

# Unified Text/Media Router
@bot.on_message(filters.private & (filters.text | filters.photo | filters.video))
async def unified_text_handler(client, message: Message):
    User_id = message.from_user.id
    
    # Admin States Handling
    If user_id in admin_states:
        State = admin_states[user_id]
        Del admin_states[user_id]
        
        If state == "wait_dash_pic":
            Pic_media = message.photo.file_id if message.photo else (message.text.strip() if message.text else None)
            If pic_media:
                Await settings_col.update_one({"type": "bot_config"}, {"$set": {"dashboard_pic": pic_media}}, upsert=True)
                Await message.reply("✅ **Dashboard Photo Updated Successfully!**")
            Else:
                Await message.reply("❌ Invalid input!")
            Return

        Elif state == "wait_dash_text":
            If message.text:
                Await settings_col.update_one({"type": "bot_config"}, {"$set": {"dashboard_text": message.text}}, upsert=True)
                Await message.reply("✅ **Dashboard Text Updated Successfully!**")
            Return

        Elif state == "wait_add_admin":
            Try:
                New_admin_id = int(message.text.strip())
                Await admins_col.update_one({"user_id": new_admin_id}, {"$set": {"user_id": new_admin_id}}, upsert=True)
                Await message.reply("✅ Admin added successfully!")
            Except Exception as e:
                Await message.reply(f"❌ Error: {e}")
            Return
        Elif state == "wait_rem_admin":
            Try:
                Rem_id = int(message.text.strip())
                Await admins_col.delete_one({"user_id": rem_id})
                Await message.reply("✅ Admin removed successfully!")
            Except Exception as e:
                Await message.reply(f"❌ Error: {e}")
            Return
        Elif state == "wait_add_fsub":
            Ch = message.text.strip()
            Await forcesub_col.update_one({"channel": ch}, {"$set": {"channel": ch}}, upsert=True)
            Await message.reply("✅ Force Sub channel added successfully!")
            Return
        Elif state == "wait_rem_fsub":
            Ch = message.text.strip()
            Await forcesub_col.delete_one({"channel": ch})
            Await message.reply("✅ Force Sub channel removed successfully!")
            Return
        Elif state == "wait_broadcast":
            Bc_text = message.text
            Users = await users_col.find().to_list(length=50000)
            Success, failed = 0, 0
            Status_msg = await message.reply("Broadcast Started...")
            For u in users:
                Try:
                    Await client.send_message(u["user_id"], bc_text)
                    Success += 1
                    Await asyncio.sleep(0.1)
                Except:
                    Failed += 1
            Await status_msg.edit_text(f"✅ **Broadcast Completed!**\n\nSuccess: `{success}`\nFailed: `{failed}`")
            Return

    If user_id not in temp_sessions:
        Return
    
    State = temp_sessions[user_id]
    
    # Custom Interval Input Flow
    If state["step"] == "waiting_custom_interval":
        Try:
            Seconds = int(message.text.strip())
            If seconds < 10:
                Await message.reply("⚠️ Interval must be at least 10 seconds!")
                Return
            Await settings_col.update_one({"user_id": user_id}, {"$set": {"interval": seconds}}, upsert=True)
            Del temp_sessions[user_id]
            Await message.reply(f"✅ **Interval updated to `{seconds}` seconds!**")
            Await show_dashboard(message)
        Except ValueError:
            Await message.reply("❌ Invalid number! Please send seconds as digits (e.g. `300`).")
        Return

    # Set Welcome Input Handler
    If state["step"] == "waiting_welcome_msg":
        Raw_text = message.caption or message.text or ""
        Media_id = None
        Media_type = None
        
        If message.photo:
            Media_id = message.photo.file_id
            Media_type = "photo"
        Elif message.video:
            Media_id = message.video.file_id
            Media_type = "video"

        Btn_text, btn_url = None, None
        If "|" in raw_text:
            Parts = [p.strip() for p in raw_text.split("|")]
            W_text = parts[0]
            If len(parts) >= 3:
                Btn_text = parts[1]
                Btn_url = parts[2]
        Else:
            W_text = raw_text

        Await welcome_col.update_one(
            {"user_id": user_id},
            {"$set": {
                "user_id": user_id,
                "text": w_text,
                "media_id": media_id,
                "media_type": media_type,
                "btn_text": btn_text,
                "btn_url": btn_url
            }},
            upsert=True
        )
        Del temp_sessions[user_id]
        Await message.reply("✅ **Welcome Message Saved Successfully!**")
        Await show_dashboard(message)
        Return

    # Add Account Steps
    If state["step"] == "waiting_phone":
        Phone = message.text.strip()
        State["phone"] = phone
        Try:
            Userbot = Client(f"temp_session_{user_id}", api_id=API_ID, api_hash=API_HASH, in_memory=True)
            Await userbot.connect()
            Sent_code = await userbot.send_code(phone)
            State["userbot"] = userbot
            State["phone_code_hash"] = sent_code.phone_code_hash
            State["step"] = "waiting_otp"
            Logger.info(f"Userbot login OTP sent for phone {phone}")
            Await message.reply("OTP has been sent to your Telegram account.\n\nEnter OTP (e.g. 1 2 3 4 5):")
        Except Exception as e:
            Logger.error(f"Userbot login send_code error: {e}")
            Await message.reply(f"❌ Error: {str(e)}\nTry again /start")
            Del temp_sessions[user_id]
            
    Elif state["step"] == "waiting_otp":
        Otp = message.text.strip().replace(" ", "")
        Userbot = state["userbot"]
        Phone = state["phone"]
        Hash_code = state["phone_code_hash"]
        
        Try:
            Await userbot.sign_in(phone, hash_code, otp)
            Session_string = await userbot.export_session_string()
            Await accounts_col.insert_one({"user_id": user_id, "phone": phone, "session_string": session_string})
            Await userbot.disconnect()
            Del temp_sessions[user_id]
            Logger.info(f"Userbot successfully logged in and added for user {user_id} ({phone})")
            
            # Ensure worker is active
            If user_id in active_workers:
                Try:
                    Active_workers[user_id].cancel()
                Except Exception:
                    Pass
            Task = asyncio.create_task(account_worker(bot, user_id))
            Active_workers[user_id] = task
            
            Await message.reply("✅ Account Added Successfully!")
            Await show_dashboard(message)
        Except SessionPasswordNeeded:
            State["step"] = "waiting_password"
            Await message.reply("Two-Step Verification detected.\n\nEnter your password:")
        Except Exception as e:
            Logger.error(f"Userbot sign_in OTP error: {e}")
            Await message.reply(f"❌ Error: {str(e)}\nStart over with /start")
            Del temp_sessions[user_id]

    Elif state["step"] == "waiting_password":
        Password = message.text.strip()
        Userbot = state["userbot"]
        Try:
            Await userbot.check_password(password)
            Session_string = await userbot.export_session_string()
            Await accounts_col.insert_one({"user_id": user_id, "phone": state["phone"], "session_string": session_string})
            Await userbot.disconnect()
            Del temp_sessions[user_id]
            Logger.info(f"Userbot successfully logged in with 2FA for user {user_id}")
            
            If user_id in active_workers:
                Try:
                    Active_workers[user_id].cancel()
                Except Exception:
                    Pass
            Task = asyncio.create_task(account_worker(bot, user_id))
            Active_workers[user_id] = task
            
            Await message.reply("✅ Account Added Successfully with 2FA!")
            Await show_dashboard(message)
        Except Exception as e:
            Logger.error(f"Userbot 2FA password error: {e}")
            Await message.reply(f"❌ Password Error: {str(e)}\nStart over with /start")
            Del temp_sessions[user_id]

    Elif state["step"] == "waiting_ad_text":
        Ad_text = message.text
        Await ads_col.update_one({"user_id": user_id}, {"$set": {"text": ad_text}}, upsert=True)
        Del temp_sessions[user_id]
        Await message.reply("✅ Advertisement Saved Successfully!")
        Await show_dashboard(message)

    Elif state["step"] == "waiting_autoreply_text":
        Ar_text = message.text
        Await settings_col.update_one({"user_id": user_id}, {"$set": {"auto_reply_text": ar_text, "auto_reply": True}}, upsert=True)
        Del temp_sessions[user_id]
        Await message.reply("✅ Auto Reply Enabled & Message Saved!")
        If user_id not in active_workers or active_workers[user_id].done():
            Task = asyncio.create_task(account_worker(bot, user_id))
            Active_workers[user_id] = task
        Await show_dashboard(message)

# --- Set Advertisement ---
@bot.on_callback_query(filters.regex("set_ad"))
async def set_ad_cb(client, callback: CallbackQuery):
    User_id = callback.from_user.id
    Temp_sessions[user_id] = {"step": "waiting_ad_text"}
    Await callback.message.reply("Send advertisement text:")

# --- Interval & Delay Menu ---
@bot.on_callback_query(filters.regex("set_interval"))
async def set_interval_cb(client, callback: CallbackQuery):
    User_id = callback.from_user.id
    User_setting = await settings_col.find_one({"user_id": user_id})
    Current_sec = user_setting.get("interval", 300) if user_setting else 300

    Caption_text = (
        "╰_╯ **SET BROADCAST CYCLE INTERVAL**\n\n"
        F"**Current Interval:** `{current_sec} seconds`\n\n"
        "**Recommended Intervals:**\n"
        "• 300s - Aggressive (5 min) 🔴\n"
        "• 600s - Safe & Balanced (10 min) 🟡\n"
        "• 1200s - Conservative (20 min) 🟢\n\n"
        "To set custom time interval click below or send a number (in seconds):\n\n"
        "*(Note: using short time interval for broadcasting can get your Account on high risk.)*"
    )

    Keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("300s (5 Min)", callback_data="int_300"), InlineKeyboardButton("600s (10 Min)", callback_data="int_600")],
        [InlineKeyboardButton("1200s (20 Min)", callback_data="int_1200"), InlineKeyboardButton("1800s (30 Min)", callback_data="int_1800")],
        [InlineKeyboardButton("✏ Custom Time", callback_data="int_custom")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_home")]
    ])
    
    Try:
        Await callback.message.edit_caption(caption=caption_text, reply_markup=keyboard)
    Except Exception:
        Await callback.message.reply(caption_text, reply_markup=keyboard)

@bot.on_callback_query(filters.regex(r"^int_"))
async def save_interval_cb(client, callback: CallbackQuery):
    User_id = callback.from_user.id
    Val = callback.data.split("_")[1]
    
    If val == "custom":
        Temp_sessions[user_id] = {"step": "waiting_custom_interval"}
        Await callback.message.reply("✏️ **Send time interval in seconds:**\n(Example: Send `300` for 5 minutes)")
        Return

    Interval_sec = int(val)
    Await settings_col.update_one({"user_id": user_id}, {"$set": {"interval": interval_sec}}, upsert=True)
    Await callback.answer(f"✅ Interval set to {interval_sec} seconds!")
    Await show_dashboard(callback, edit=True)

# --- Auto Reply Menu ---
@bot.on_callback_query(filters.regex("auto_reply"))
async def auto_reply_menu(client, callback: CallbackQuery):
    Keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Enable 🟢", callback_data="ar_enable"), InlineKeyboardButton("Disable 🔴", callback_data="ar_disable")],
        [InlineKeyboardButton("Edit Message 📝", callback_data="ar_edit")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_home")]
    ])
    Await callback.message.edit_caption(caption="🤖 **Auto Reply Settings**\nConfigure automated response for incoming direct messages on your userbots.", reply_markup=keyboard)

@bot.on_callback_query(filters.regex("ar_enable"))
async def ar_enable_cb(client, callback: CallbackQuery):
    User_id = callback.from_user.id
    Await settings_col.update_one({"user_id": user_id}, {"$set": {"auto_reply": True}}, upsert=True)
    
    If user_id not in active_workers or active_workers[user_id].done():
        Task = asyncio.create_task(account_worker(bot, user_id))
        Active_workers[user_id] = task

    Await callback.answer("✅ Auto Reply Enabled")
    Logger.info(f"Auto-reply enabled for user {user_id}")
    Await show_dashboard(callback, edit=True)

@bot.on_callback_query(filters.regex("ar_disable"))
async def ar_disable_cb(client, callback: CallbackQuery):
    Await settings_col.update_one({"user_id": callback.from_user.id}, {"$set": {"auto_reply": False}}, upsert=True)
    Await callback.answer("❌ Auto Reply Disabled")
    Logger.info(f"Auto-reply disabled for user {callback.from_user.id}")
    Await show_dashboard(callback, edit=True)

@bot.on_callback_query(filters.regex("ar_edit"))
async def ar_edit_cb(client, callback: CallbackQuery):
    Temp_sessions[callback.from_user.id] = {"step": "waiting_autoreply_text"}
    Await callback.message.reply("Send your auto-reply message text:")

# --- Robust Account Worker with Fault Tolerance & Welcome/Auto-Reply Logic ---
async def account_worker(bot_client, user_id):
    Log_msg = None
    Userbot = None
    Logger.info(f"Worker task initialized for user {user_id}")
    
    While True:
        Try:
            Account = await accounts_col.find_one({"user_id": user_id})
            If not account:
                Logger.info(f"No accounts found for user {user_id}. Worker terminating.")
                Break
                
            If userbot is None or not userbot.is_connected:
                Userbot = Client(
                    F"worker_{user_id}", 
                    Session_string=account["session_string"], 
                    Api_id=API_ID, 
                    Api_hash=API_HASH, 
                    In_memory=True
                )
                Await userbot.start()
                Logger.info(f"Userbot connected successfully for user {user_id}")

            # Update Bio once if not set
            User_db_data = await users_col.find_one({"user_id": user_id})
            If user_db_data and not user_db_data.get("bio_set", False):
                Try:
                    Await userbot.invoke(UpdateProfile(about="Free Auto ads via @adsmanage13_bot"))
                    Await users_col.update_one({"user_id": user_id}, {"$set": {"bio_set": True}})
                Except Exception as bio_err:
                    Logger.error(f"Bio set error for user {user_id}: {bio_err}")

            Discovered_groups = set()

            @userbot.on_message(filters.group)
            async def live_group_harvester(client, message):
                If message.chat:
                    Discovered_groups.add((message.chat.id, message.chat.title or "Unnamed Group"))

            # --- Userbot Welcome & Auto-Reply Handler for Private DMs ---
            @userbot.on_message(filters.private & ~filters.me & ~filters.bot)
            async def userbot_dm_handler(client, message):
                Try:
                    Sender_id = message.from_user.id
                    Userbot_me = await client.get_me()
                    Userbot_id = userbot_me.id

                    # Check if already welcomed in private DM for this specific userbot
                    Welcomed = await welcomed_dms_col.find_one({"userbot_id": userbot_id, "sender_id": sender_id})
                    
                    If not welcomed:
                        # Fetch custom welcome message configuration from main bot settings
                        W_data = await welcome_col.find_one({"user_id": user_id}) or await welcome_col.find_one({"type": "default"})
                        
                        Default_welcome_text = (
                            F"👋 **Hello {message.from_user.first_name or 'User'}! Welcome.**\n\n"
                            "🤖 This is an automated account managed via Ads Manager Bot."
                        )
                        
                        Welcome_text = w_data.get("text", default_welcome_text) if w_data else default_welcome_text
                        Media_id = w_data.get("media_id") if w_data else None
                        Media_type = w_data.get("media_type") if w_data else None
                        Custom_button_text = w_data.get("btn_text", "🚀 Open Bot") if w_data else "🚀 Open Bot"
                        Custom_button_url = w_data.get("btn_url") if w_data else None

                        Buttons = []
                        If custom_button_url:
                            Buttons.append([InlineKeyboardButton(custom_button_text, url=custom_button_url)])
                        
                        Keyboard = InlineKeyboardMarkup(buttons) if buttons else None

                        If media_id and media_type == "photo":
                            Await message.reply_photo(photo=media_id, caption=welcome_text, reply_markup=keyboard)
                        Elif media_id and media_type == "video":
                            Await message.reply_video(video=media_id, caption=welcome_text, reply_markup=keyboard)
                        Else:
                            Await message.reply_text(welcome_text, reply_markup=keyboard)

                        # Mark as welcomed so it never triggers again for this sender on this userbot
                        Await welcomed_dms_col.insert_one({"userbot_id": userbot_id, "sender_id": sender_id})
                        Logger.info(f"Welcome message sent to DM sender {sender_id} by userbot {userbot_id}")
                        Return

                    # Subsequent messages: Trigger Auto-Reply if enabled
                    User_settings = await settings_col.find_one({"user_id": user_id})
                    If user_settings and user_settings.get("auto_reply", False):
                        Ar_text = user_settings.get("auto_reply_text")
                        If ar_text:
                            Await message.reply_text(ar_text)
                            Logger.info(f"Auto-reply triggered for userbot {userbot_id} to sender {sender_id}")
                Except Exception as e:
                    Logger.error(f"Userbot DM Handler Error for user {user_id}: {e}")

            While True:
                Settings = await settings_col.find_one({"user_id": user_id})
                If not settings:
                    Await asyncio.sleep(5)
                    Continue

                Ad_status = settings.get("ad_status", "Stopped ⛔")
                
                # If ads are not running, keep userbot alive for Auto-Reply / Harvesting without broadcasting
                If ad_status != "Running 🚀":
                    Await asyncio.sleep(5)
                    Continue

                If not log_msg:
                    Try:
                        Log_msg = await bot_client.send_message(user_id, "🚀 **Ad Worker Initialized!**\nPreparing campaign logs...")
                    Except Exception:
                        Pass

                Ad = await ads_col.find_one({"user_id": user_id})
                If not ad:
                    If log_msg:
                        Try:
                            Await log_msg.edit_text("❌ **Error:** Advertisement text missing!")
                        Except Exception:
                            Pass
                    Await asyncio.sleep(10)
                    Continue

                Sent_count, failed_count = 0, 0
                Fetched_groups_info = ""
                Chat_ids_to_target = set()
                
                Try:
                    R = await userbot.invoke(GetDialogs(offset_date=0, offset_id=0, offset_peer=InputPeerEmpty(), limit=500, hash=0))
                    For chat in r.chats:
                        If hasattr(chat, "title") and (chat.__class__.__name__ in ["Chat", "Channel"]):
                            If chat.__class__.__name__ == "Channel":
                                If getattr(chat, "megagroup", False):
                                    Chat_ids_to_target.add((int(f"-100{chat.id}"), chat.title))
                            Else:
                                Chat_ids_to_target.add((int(f"-{chat.id}"), chat.title))
                Except Exception as raw_err:
                    Logger.error(f"Raw MTProto dialog fetch error for user {user_id}: {raw_err}")

                For g_id, g_title in discovered_groups:
                    Chat_ids_to_target.add((g_id, g_title))

                Dialog_count = len(chat_ids_to_target)

                If dialog_count == 0:
                    If log_msg:
                        Try:
                            Await log_msg.edit_text("⏳ **Listening for active group chats...**")
                        Except Exception:
                            Pass
                    Await asyncio.sleep(20)
                    Continue

                # BROADCAST LOOP WITH INSTANT STOP CHECK
                Stopped_midway = False
                For chat_id, chat_title in chat_ids_to_target:
                    Current_settings = await settings_col.find_one({"user_id": user_id})
                    If not current_settings or current_settings.get("ad_status") != "Running 🚀":
                        Stopped_midway = True
                        Break

                    Try:
                        Await userbot.send_message(chat_id, ad["text"])
                        Sent_count += 1
                        Fetched_groups_info += f"\n• {chat_title} ➔ Sent ✅"
                    Except FloodWait as fw:
                        Logger.warning(f"FloodWait encountered for user {user_id}: sleeping {fw.value}s")
                        Await asyncio.sleep(fw.value)
                        Try:
                            Await userbot.send_message(chat_id, ad["text"])
                            Sent_count += 1
                            Fetched_groups_info += f"\n• {chat_title} ➔ Sent ✅"
                        Except Exception:
                            Failed_count += 1
                            Fetched_groups_info += f"\n• {chat_title} ➔ Failed ❌"
                    Except Exception:
                        Failed_count += 1
                        Fetched_groups_info += f"\n• {chat_title} ➔ Failed ❌"

                    Live_status_text = (
                        f"📢 **Live Broadcasting In Progress...**\n\n"
                        f"• Total Target Groups: `{dialog_count}`\n"
                        f"• Successfully Sent: `{sent_count}` ✅\n"
                        f"• Failed / Restricted: `{failed_count}` ❌\n\n"
                        f"📋 **Live Send Logs:**\n"
                        f"{fetched_groups_info[-2000:]}"
                    )
                    If log_msg:
                        Try:
                            Await log_msg.edit_text(live_status_text)
                        Except Exception:
                            Pass
                    
                    Await asyncio.sleep(3)

                If stopped_midway:
                    If log_msg:
                        Try:
                            Await log_msg.edit_text("⛔ **Ad Campaign Stopped.**")
                        Except Exception:
                            Pass
                    Log_msg = None
                    Continue

                Cycle_summary_text = (
                    f"📊 **Cycle Completed! Sleeping for Interval...**\n\n"
                    f"• Total Groups: `{dialog_count}`\n"
                    f"• Sent: `{sent_count}` ✅\n"
                    f"• Failed: `{failed_count}` ❌\n\n"
                    f"📋 **Final Logs:**\n"
                    f"{fetched_groups_info[-2000:]}"
                )
                If log_msg:
                    Try:
                        Await log_msg.edit_text(cycle_summary_text)
                    Except Exception:
                        Pass
                Log_msg = None

                # Interval sleep with status check chunks
                Interval_sec = settings.get("interval", 300)
                Elapsed = 0
                While elapsed < interval_sec:
                    Await asyncio.sleep(5)
                    Elapsed += 5
                    Chk = await settings_col.find_one({"user_id": user_id})
                    If not chk or chk.get("ad_status") != "Running 🚀":
                        Break

        Except Exception as worker_err:
            Logger.error(f"Worker crashed for user {user_id}: {worker_err}. Attempting auto-restart in 10 seconds...")
            Await asyncio.sleep(10)
        Finally:
            If userbot:
                Try:
                    Await userbot.stop()
                Except Exception:
                    Pass
                Userbot = None

@bot.on_callback_query(filters.regex("run_ads"))
async def run_ads_cb(client, callback: CallbackQuery):
    User_id = callback.from_user.id
    Ad = await ads_col.find_one({"user_id": user_id})
    Acc = await accounts_col.find_one({"user_id": user_id})
    
    If not ad or not acc:
        Await callback.answer("⚠️ Set ad & account first!", show_alert=True)
        Return
        
    Await settings_col.update_one({"user_id": user_id}, {"$set": {"ad_status": "Running 🚀"}}, upsert=True)
    If user_id in active_workers:
        Try:
            Active_workers[user_id].cancel()
        Except Exception:
            Pass

    Task = asyncio.create_task(account_worker(bot, user_id))
    Active_workers[user_id] = task
    Logger.info(f"Ads manually started for user {user_id}")
    Await callback.answer("🚀 Started!")
    Await show_dashboard(callback, edit=True)

@bot.on_callback_query(filters.regex("stop_ads"))
async def stop_ads_cb(client, callback: CallbackQuery):
    User_id = callback.from_user.id
    Await settings_col.update_one({"user_id": user_id}, {"$set": {"ad_status": "Stopped ⛔"}}, upsert=True)
    If user_id in active_workers:
        Try:
            Active_workers[user_id].cancel()
        Except Exception:
            Pass
        Del active_workers[user_id]
    Logger.info(f"Ads manually stopped for user {user_id}")
    Await callback.answer("⛔ Stopped!")
    Await show_dashboard(callback, edit=True)

# --- About Bot Handler ---
@bot.on_callback_query(filters.regex("about_bot"))
async def about_cb(client, callback: CallbackQuery):
    About_text = (
        "🤖 **ABOUT ADS MANAGER BOT**\n\n"
        "Welcome to the ultimate **Telegram Ads & Broadcast Manager Bot**! "
        "Is bot ki madad se aap apne Multiple Telegram Accounts ko manage kar sakte hain "
        "aur automated broadcasting & auto-reply features ka use kar sakte hain.\n\n"
        "✨ **Key Features:**\n"
        "• 📱 Multi-Account Hosting Support\n"
        "• 📢 Automated Group Ads Broadcasting\n"
        "• ⏱ Customizable Broadcast Intervals & Delays\n"
        "• 👋 Custom Welcome Message & Buttons\n"
        "• 🤖 Smart Auto Reply System\n"
        "• 📊 Real-time Live Logs & Reports\n\n"
        "👨‍💻 **Developer:** @PANDA_1125\n"
        "💬 **Support & Inquiries:** Contact Developer for custom bot setups or help!\n\n"
        "─── **Powered by @PANDA_1125** ───"
    )
    Keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👨‍‍💻 Developer", url="https://t.me/PANDA_1125")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_home")]
    ])
    Await callback.message.edit_caption(caption=about_text, reply_markup=keyboard)

@bot.on_callback_query(filters.regex("back_home"))
async def back_home_cb(client, callback: CallbackQuery):
    Await show_dashboard(callback, edit=True)

# --- Admin Panel & User Accounts Feature ---
@bot.on_callback_query(filters.regex("^open_admin_panel$"))
async def open_admin_panel_cb(client, callback: CallbackQuery):
    If not await is_admin(callback.from_user.id):
        Await callback.answer("Unauthorized!", show_alert=True)
        Return

    Keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🖼 Set Photo", callback_data="adm_set_pic"), InlineKeyboardButton("📝 Edit Text", callback_data="adm_set_text")],
        [InlineKeyboardButton("👑 Add Admin", callback_data="adm_add"), InlineKeyboardButton("❌ Remove Admin", callback_data="adm_rem")],
        [InlineKeyboardButton("📋 Admin List", callback_data="adm_list"), InlineKeyboardButton("🔒 Add Force Sub", callback_data="fsub_add")],
        [InlineKeyboardButton("🔓 Remove Force Sub", callback_data="fsub_rem"), InlineKeyboardButton("📋 Force Sub List", callback_data="fsub_list")],
        [InlineKeyboardButton("👥 User Accounts", callback_data="adm_users_page_0")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="adm_bc"), InlineKeyboardButton("📊 Statistics", callback_data="adm_stats")],
        [InlineKeyboardButton("🔙 Back to Dashboard", callback_data="back_home")]
    ])
    Await callback.message.edit_caption(caption="👑 **Admin Control Panel**", reply_markup=keyboard)

@bot.on_callback_query(filters.regex(r"^(adm_|fsub_|back_admin)"))
async def admin_buttons_cb(client, callback: CallbackQuery):
    If not await is_admin(callback.from_user.id):
        Await callback.answer("Unauthorized!", show_alert=True)
        Return
        
    Data = callback.data
    User_id = callback.from_user.id
    
    If data == "adm_set_pic":
        Admin_states[user_id] = "wait_dash_pic"
        Await callback.message.reply("Send photo OR direct photo URL to set as dashboard image:")
    Elif data == "adm_set_text":
        Admin_states[user_id] = "wait_dash_text"
        Instruction = (
            "Send the new text for Dashboard.\n\n"
            "You can use these placeholders to insert dynamic stats:\n"
            "• `{acc_count}` - Number of hosted accounts\n"
            "• `{service_status}` - Status of ad (Set/Not set)\n"
            "• `{ad_status}` - Ad running status\n"
            "• `{interval}` - Interval in seconds"
        )
        Await callback.message.reply(instruction)
    Elif data == "adm_add":
        Admin_states[user_id] = "wait_add_admin"
        Await callback.message.reply("Send the Telegram User ID of the new admin:")
    Elif data == "adm_rem":
        Admin_states[user_id] = "wait_rem_admin"
        Await callback.message.reply("Send the Telegram User ID of the admin to remove:")
    Elif data == "adm_list":
        Admins = await admins_col.find().to_list(length=100)
        Text = f"📋 **Admin List:**\nPrimary Admin: `{PRIMARY_ADMIN_ID}`\n"
        For a in admins:
            Text += f"- `{a['user_id']}`\n"
        Await callback.message.edit_caption(caption=text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="open_admin_panel")]]))
    Elif data.startswith("adm_users_page_"):
        Page = int(data.split("_")[-1])
        Limit = 5
        Users_list = await users_col.find().skip(page * limit).limit(limit).to_list(length=limit)
        Total_users = await users_col.count_documents({})
        
        If not users_list and page > 0:
            Page = 0
            Users_list = await users_col.find().skip(0).limit(limit).to_list(length=limit)

        Text = f"👥 **Registered User Accounts** (Page `{page + 1}` / `{(total_users + limit - 1) // limit or 1}`):\n\n"
        
        For u in users_list:
            Uid = u.get("user_id")
            Name = u.get("first_name", "User")
            Uname = u.get("username", "")
            Uname_str = f"@{uname}" if uname else "N/A"
            Profile_link = f"tg://user?id={uid}"
            
            Accs = await accounts_col.find({"user_id": uid}).to_list(length=20)
            Acc_count = len(accs)
            
            Text += f"👤 User: {name}\n"
            Text += f"🆔 ID: `{uid}`\n"
            Text += f"📛 Username: {uname_str}\n"
            Text += f"🔗 Profile: {profile_link}\n"
            
            If accs:
                Text += "📱 Hosted Accounts:\n"
                For acc in accs:
                    Text += f"• `{acc.get('phone')}`\n"
            Else:
                Text += "📱 Hosted Accounts: None\n"
                
            Text += f"Total Accounts: `{acc_count}`\n\n"
            
        Nav_buttons = []
        If page > 0:
            Nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"adm_users_page_{page - 1}"))
        If (page + 1) * limit < total_users:
            Nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"adm_users_page_{page + 1}"))
            
        Keyboard_rows = []
        If nav_buttons:
            Keyboard_rows.append(nav_buttons)
        Keyboard_rows.append([InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="open_admin_panel")])
        
        Await callback.message.edit_caption(caption=text, reply_markup=InlineKeyboardMarkup(keyboard_rows))
    Elif data == "fsub_add":
        Admin_states[user_id] = "wait_add_fsub"
        Await callback.message.reply("Send channel username or private ID (`@channel` or `-100xxx`):")
    Elif data == "fsub_rem":
        Admin_states[user_id] = "wait_rem_fsub"
        Await callback.message.reply("Send channel username or ID to remove:")
    Elif data == "fsub_list":
        Subs = await forcesub_col.find().to_list(length=100)
        Text = "📋 **Force Sub Channels:**\n"
        For s in subs:
            Text += f"- `{s['channel']}`\n"
        Await callback.message.edit_caption(caption=text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="open_admin_panel")]]))
    Elif data == "adm_bc":
        Admin_states[user_id] = "wait_broadcast"
        Await callback.message.reply("Send the broadcast message:")
    Elif data == "adm_stats":
        Total_users = await users_col.count_documents({})
        Total_accs = await accounts_col.count_documents({})
        Text = f"📊 **Bot Statistics:**\n\nTotal Users: `{total_users}`\nHosted Accounts: `{total_accs}`"
        Await callback.message.edit_caption(caption=text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="open_admin_panel")]]))

# --- Startup Worker Recovery Hook ---
async def restore_active_workers():
    Await asyncio.sleep(3)
    Try:
        Cursor = settings_col.find({"ad_status": "Running 🚀"})
        Async for setting in cursor:
            User_id = setting.get("user_id")
            If user_id and user_id not in active_workers:
                Acc_exists = await accounts_col.find_one({"user_id": user_id})
                If acc_exists:
                    Task = asyncio.create_task(account_worker(bot, user_id))
                    Active_workers[user_id] = task
                    Logger.info(f"Restored active background worker for user {user_id} upon startup.")
    Except Exception as e:
        Logger.error(f"Error restoring active workers: {e}")

# --- Main Entry Point ---
If __name__ == "__main__":
    Import threading
    Flask_thread = threading.Thread(target=run_flask)
    Flask_thread.daemon = True
    Flask_thread.start()
    
    @bot.on_raw_update()
    async def startup_hook(client, update, users, chats):
        Global worker_restored
        Try:
            If not globals().get("worker_restored", False):
                Globals()["worker_restored"] = True
                Asyncio.create_task(restore_active_workers())
        Except Exception:
            Pass

    Print("Bot is starting...")
    Bot.run()
