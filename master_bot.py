import asyncio
import os
from pyrogram import Client, filters
from pyrogram.storage import StringSession # Yeh import add karein
from database import save_session, get_session, add_worker, get_all_workers


# --- Configuration (Using Environment Variables for Railway) --- #
MASTER_BOT_TOKEN = os.getenv("MASTER_BOT_TOKEN")
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH")

if not MASTER_BOT_TOKEN or not API_ID or not API_HASH:
    print("ERROR: MASTER_BOT_TOKEN, API_ID, and API_HASH must be set in Environment Variables!")
    exit(1)

# --- Initialize Database --- #
init_db()

# --- Master Bot Client --- #
master_bot = Client(
    "master_bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=MASTER_BOT_TOKEN,
    workdir=DATA_DIR # Store master session in data dir
)

async def get_worker_client(phone_number):
    session_str = get_session(phone_number) # Firebase se string fetch karega
    return Client(
        f"{phone_number}", 
        api_id=API_ID, 
        api_hash=API_HASH, 
        session_string=session_str or "" # String session yahan use hoga
    )

# --- Helper Functions --- #
async def send_login_request(client, phone_number, message):
    try:
        await client.connect()
        if not await client.is_user_connected():
            sent_code = await client.send_code(phone_number)
            await message.reply_text(
                f"Verification code sent to {phone_number}. Please enter it like: `/code 12345`"
            )
            return sent_code.phone_code_hash
        else:
            await message.reply_text(f"Account {phone_number} is already logged in.")
            return None
    except FloodWait as e:
        await message.reply_text(f"Flood wait for {phone_number}: {e.value} seconds. Please try again later.")
        return None
    except Exception as e:
        await message.reply_text(f"Error sending code to {phone_number}: {e}")
        return None

async def complete_login(client, phone_number, phone_code_hash, phone_code, message):
    try:
        await client.sign_in(phone_number, phone_code_hash, phone_code)
        # Store just the phone number, we know where the sessions are
                # --- YE NAYA PART HAI ---
        session_string = await client.export_session_string() # Session export karein
        save_session(phone_number, session_string)             # Firebase mein save karein
        add_worker(phone_number)                               # Worker list mein add karein
        # ----------------------
        await message.reply_text(f"Successfully logged in {phone_number} and added to workers.")
        return True
    except PhoneCodeInvalid:
        await message.reply_text(f"Invalid phone code for {phone_number}. Please try again with `/code 12345`")
        return False
    except SessionPasswordNeeded:
        await message.reply_text(f"Two-step verification enabled for {phone_number}. Please enter password like: `/password your_password`")
        return False
    except Exception as e:
        await message.reply_text(f"Error completing login for {phone_number}: {e}")
        return False
    finally:
        await client.disconnect()

# --- Global state for login process --- #
PENDING_LOGINS = {}

# --- Command Handlers --- #
@master_bot.on_message(filters.command("start"))
async def start_command(client, message):
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Add New Account", callback_data="add_account")],
            [InlineKeyboardButton("⚙️ Manage All Accounts", callback_data="manage_accounts")],
            [InlineKeyboardButton("👤 My Accounts", callback_data="my_accounts")],
            [InlineKeyboardButton("🤖 Auto-Task Bot", callback_data="auto_task_bot")]
        ]
    )
    await message.reply_text(
        "Hello! I am your Master Telegram Bot on Railway. How can I help you?",
        reply_markup=keyboard
    )

@master_bot.on_message(filters.command("add"))
async def add_account_command(client, message):
    if len(message.command) < 2:
        await message.reply_text("Please provide the phone number. Example: `/add +1234567890`")
        return
    
    phone_number = message.command[1]
    worker_client = await get_worker_client(phone_number)
    phone_code_hash = await send_login_request(worker_client, phone_number, message)
    if phone_code_hash:
        PENDING_LOGINS[message.from_user.id] = {
            'phone_number': phone_number,
            'phone_code_hash': phone_code_hash,
            'client': worker_client
        }

@master_bot.on_message(filters.command("code"))
async def code_command(client, message):
    user_id = message.from_user.id
    if user_id not in PENDING_LOGINS:
        await message.reply_text("No pending login request.")
        return
    
    if len(message.command) < 2:
        await message.reply_text("Please provide the code. Example: `/code 12345`")
        return
    
    phone_code = message.command[1]
    login_data = PENDING_LOGINS[user_id]
    
    success = await complete_login(
        login_data['client'],
        login_data['phone_number'],
        login_data['phone_code_hash'],
        phone_code,
        message
    )
    if success:
        del PENDING_LOGINS[user_id]

@master_bot.on_message(filters.command("password"))
async def password_command(client, message):
    user_id = message.from_user.id
    if user_id not in PENDING_LOGINS:
        await message.reply_text("No pending login request.")
        return
    
    if len(message.command) < 2:
        await message.reply_text("Please provide your 2FA password.")
        return
    
    password = message.command[1]
    login_data = PENDING_LOGINS[user_id]
    
    try:
        await login_data['client'].check_password(password)
        add_worker(login_data['phone_number'], login_data['phone_number'])
        await message.reply_text(f"Successfully logged in {login_data['phone_number']} with 2FA.")
        del PENDING_LOGINS[user_id]
    except Exception as e:
        await message.reply_text(f"Error with 2FA: {e}")
    finally:
        await login_data['client'].disconnect()

# --- Callback Query Handlers --- #
@master_bot.on_callback_query()
async def callback_query_handler(client, callback_query):
    data = callback_query.data
    if data == "add_account":
        await callback_query.message.reply_text("Use `/add +1234567890` to add an account.")
    elif data in ["manage_accounts", "my_accounts"]:
        workers = get_all_workers()
        if not workers:
            await callback_query.message.reply_text("No accounts added.")
        else:
            text = "Your accounts:\n" + "\n".join([f"- {w[0]}" for w in workers])
            await callback_query.message.reply_text(text)
    elif data == "auto_task_bot":
        await callback_query.message.reply_text("Use `/autotask @bot https://t.me/channel` to start.")
    await callback_query.answer()

# --- Worker Logic --- #
async def perform_worker_actions(phone_number, target_channel_link, target_bot_username, message):
    session_path = os.path.join(DATA_DIR, "sessions")
    app = Client(phone_number, API_ID, API_HASH, workdir=session_path)
    
    try:
        await app.start()
        # Join Channel
        try:
            await app.join_chat(target_channel_link)
        except: pass

        # Interact with Bot
        try:
            await app.send_message(target_bot_username, "/start")
            await asyncio.sleep(3)
            async for bot_msg in app.get_chat_history(target_bot_username, limit=3):
                if bot_msg.reply_markup:
                    for row in bot_msg.reply_markup.inline_keyboard:
                        for btn in row:
                            if any(k in btn.text.lower() for k in ["joined", "verify", "check", "done", "confirm"]):
                                try: await bot_msg.click(btn.text)
                                except: pass
        except: pass
    except Exception as e:
        print(f"Error for {phone_number}: {e}")
    finally:
        await app.stop()

# --- Auto-Task Logic --- #
@master_bot.on_message(filters.command("autotask"))
async def autotask_command(client, message):
    if len(message.command) < 3:
        await message.reply_text("Usage: `/autotask @bot https://t.me/channel`")
        return
    
    target_bot = message.command[1]
    target_channel = message.command[2]
    await message.reply_text(f"🚀 Starting task for {target_bot}...")

    workers = get_all_workers()
    if not workers:
        await message.reply_text("❌ No workers.")
        return

    tasks = [perform_worker_actions(w[0], target_channel, target_bot, message) for w in workers]
    await asyncio.gather(*tasks, return_exceptions=True)
    await message.reply_text(f"✅ Done for {len(workers)} accounts.")

if __name__ == "__main__":
    print("Master Bot starting on Railway...")
    master_bot.run()
