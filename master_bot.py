
import asyncio
import os
import sqlite3
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, FloodWait

from database import init_db, add_worker, get_all_workers, remove_worker

# --- Configuration --- #
# Master Bot API Token (from BotFather)
MASTER_BOT_TOKEN = "8927642493:AAHbRfihDlpDIpa1OPPLstTIalp4sKsyIBU"  # <<< IMPORTANT: Replace with your Master Bot's token

# Telegram API ID and HASH for worker accounts (from my.telegram.org)
API_ID = 1234567  # <<< IMPORTANT: Replace with your API ID
API_HASH = "your_api_hash"  # <<< IMPORTANT: Replace with your API Hash

# --- Initialize Database --- #
init_db()

# --- Master Bot Client --- #
master_bot = Client(
    "master_bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=MASTER_BOT_TOKEN
)

# --- Worker Account Client Factory --- #
async def get_worker_client(phone_number):
    session_name = f"sessions/{phone_number}"
    # Ensure sessions directory exists
    os.makedirs("sessions", exist_ok=True)
    return Client(session_name, API_ID, API_HASH, phone_number=phone_number)

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
        add_worker(phone_number, client.session_name)
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
# Store pending login attempts: {user_id: {'phone_number': '...', 'phone_code_hash': '...', 'client': Client}}
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
        "Hello! I am your Master Telegram Bot. How can I help you?",
        reply_markup=keyboard
    )

@master_bot.on_message(filters.command("add"))
async def add_account_command(client, message):
    if len(message.command) < 2:
        await message.reply_text("Please provide the phone number after the command. Example: `/add +1234567890`")
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
        await message.reply_text("No pending login request. Please use `/add <phone_number>` first.")
        return
    
    if len(message.command) < 2:
        await message.reply_text("Please provide the verification code. Example: `/code 12345`")
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
        await message.reply_text("No pending login request. Please use `/add <phone_number>` first.")
        return
    
    if len(message.command) < 2:
        await message.reply_text("Please provide your 2FA password. Example: `/password your_password`")
        return
    
    password = message.command[1]
    login_data = PENDING_LOGINS[user_id]
    
    try:
        await login_data['client'].check_password(password)
        add_worker(login_data['phone_number'], login_data['client'].session_name)
        await message.reply_text(f"Successfully logged in {login_data['phone_number']} with 2FA and added to workers.")
        del PENDING_LOGINS[user_id]
    except Exception as e:
        await message.reply_text(f"Error with 2FA password: {e}. Please try again.")
    finally:
        await login_data['client'].disconnect()

# --- Callback Query Handlers --- #
@master_bot.on_callback_query()
async def callback_query_handler(client, callback_query):
    data = callback_query.data
    user_id = callback_query.from_user.id

    if data == "add_account":
        await callback_query.message.reply_text(
            "To add a new account, please send its phone number with country code. Example: `/add +1234567890`"
        )
    elif data == "manage_accounts" or data == "my_accounts":
        workers = get_all_workers()
        if not workers:
            await callback_query.message.reply_text("No worker accounts added yet.")
            return
        
        account_list = "Your registered accounts:\n"
        for phone, _ in workers:
            account_list += f"- {phone}\n"
        await callback_query.message.reply_text(account_list)

    elif data == "auto_task_bot":
        await callback_query.message.reply_text(
            "Please send the username of the target bot (e.g., `@target_bot`) and the channel link (e.g., `https://t.me/channel_link`) you want all accounts to join and verify. Example: `/autotask @target_bot https://t.me/channel_link`"
        )
    
    await callback_query.answer() # Acknowledge the callback query

# --- Worker Logic --- #
async def perform_worker_actions(phone_number, target_channel_link, target_bot_username, message):
    session_name = f"sessions/{phone_number}"
    app = Client(session_name, API_ID, API_HASH)
    
    try:
        await app.start()
        
        # 1. Join Channel
        try:
            await app.join_chat(target_channel_link)
            print(f"[{phone_number}] Joined channel {target_channel_link}")
        except Exception as e:
            print(f"[{phone_number}] Error joining channel: {e}")

        # 2. Interact with Bot
        try:
            # Start the bot
            await app.send_message(target_bot_username, "/start")
            await asyncio.sleep(2) # Wait for bot to respond
            
            # Find and click 'Joined' or 'Verify' buttons if they exist
            # This part is dynamic. We'll look for common button texts.
            async for bot_message in app.get_chat_history(target_bot_username, limit=3):
                if bot_message.reply_markup:
                    for row in bot_message.reply_markup.inline_keyboard:
                        for button in row:
                            if any(keyword in button.text.lower() for keyword in ["joined", "verify", "check", "done", "confirm"]):
                                try:
                                    await bot_message.click(button.text)
                                    print(f"[{phone_number}] Clicked button: {button.text}")
                                    await asyncio.sleep(1)
                                except Exception as e:
                                    print(f"[{phone_number}] Error clicking button {button.text}: {e}")
            
            print(f"[{phone_number}] Sent /start and attempted verification with {target_bot_username}")
        except Exception as e:
            print(f"[{phone_number}] Error interacting with bot: {e}")

    except FloodWait as e:
        await message.reply_text(f"Flood wait for {phone_number}: {e.value} seconds.")
    except Exception as e:
        print(f"[{phone_number}] Unexpected error: {e}")
    finally:
        await app.stop()

# --- Auto-Task Logic --- #
@master_bot.on_message(filters.command("autotask"))
async def autotask_command(client, message):
    if len(message.command) < 3:
        await message.reply_text("Please provide the target bot username and channel link. Example: `/autotask @target_bot https://t.me/channel_link`")
        return
    
    target_bot_username = message.command[1]
    target_channel_link = message.command[2]

    await message.reply_text(f"🚀 Starting auto-task for {target_bot_username} and {target_channel_link} with all worker accounts...")

    workers = get_all_workers()
    if not workers:
        await message.reply_text("❌ No worker accounts registered.")
        return

    # Process workers in batches or concurrently
    tasks = []
    for phone_number, _ in workers:
        tasks.append(perform_worker_actions(phone_number, target_channel_link, target_bot_username, message))
    
    # Run all tasks concurrently (asyncio.gather)
    # Note: Running 50 accounts concurrently might hit rate limits, consider chunking
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    await message.reply_text(f"✅ Auto-task completed for all {len(workers)} worker accounts.")


# --- Main Run --- #
if __name__ == "__main__":
    print("Master Bot starting...")
    master_bot.run()
