import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, ChatMemberUpdatedFilter, IS_NOT_MEMBER, IS_MEMBER
from aiogram.types import Message, ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError

from config import config
from database import db
from spam_detector import spam_detector

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize bot and dispatcher
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()

# Helper functions
async def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS

async def check_subscription(user_id: int) -> bool:
    return await db.check_subscription(user_id)

async def get_group_settings(group_id: int) -> dict:
    group = await db.get_group(group_id)
    if group:
        return group.settings
    return {}

# Command handlers
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user = await db.create_user(message.from_user.id, message.from_user.username)
    
    welcome_text = """
🤖 <b>Welcome to GroupGuard Bot!</b>

I help manage Telegram groups with:
• 🛡️ Spam & link protection
• 👋 Auto-welcome messages  
• 📊 Group analytics
• 🔇 Auto-moderation

<b>Getting Started:</b>
1. Add me to your group
2. Make me an admin with delete messages & ban permissions
3. Use /activate in the group
4. Ensure you have an active subscription

<b>Commands:</b>
/activate - Activate bot in group (requires subscription)
/status - Check bot status and your subscription
/stats - View group analytics
/settings - Configure group settings

Need help? Contact support.
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add to Group", url=f"https://t.me/{(await bot.me()).username}?startgroup=true")],
        [InlineKeyboardButton(text="💳 Get Subscription", callback_data="subscribe")]
    ])
    
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")

@dp.message(Command("activate"))
async def cmd_activate(message: Message):
    if message.chat.type == 'private':
        await message.answer("❌ This command only works in groups!")
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Check if user has subscription
    if not await check_subscription(user_id):
        await message.answer(
            "❌ <b>Subscription Required</b>\n\n"
            "You need an active subscription to activate this bot.\n"
            "Contact admin to purchase access.",
            parse_mode="HTML"
        )
        return
    
    # Check bot permissions
    try:
        bot_member = await bot.get_chat_member(chat_id, bot.id)
        if bot_member.status != ChatMemberStatus.ADMINISTRATOR:
            await message.answer("❌ Please make me an administrator first!")
            return
        
        if not bot_member.can_delete_messages:
            await message.answer("❌ I need permission to delete messages!")
            return
            
    except TelegramAPIError:
        await message.answer("❌ Could not verify permissions. Please add me as admin.")
        return
    
    # Activate group
    await db.add_group(chat_id, message.chat.title or "Unknown", user_id)
    
    await message.answer(
        "✅ <b>Bot Activated!</b>\n\n"
        f"Group: {message.chat.title}\n"
        f"Activated by: {message.from_user.full_name}\n\n"
        "Features enabled:\n"
        "• Anti-spam protection\n"
        "• Link filtering\n"
        "• Welcome messages\n"
        "• Auto-moderation\n\n"
        "Use /settings to customize.",
        parse_mode="HTML"
    )

@dp.message(Command("status"))
async def cmd_status(message: Message):
    user = await db.get_user(message.from_user.id)
    
    if not user:
        await message.answer("❌ User not found. Start the bot with /start")
        return
    
    # Check subscription
    is_active = await check_subscription(message.from_user.id)
    sub_status = "✅ Active" if is_active else "❌ Inactive"
    
    if user.subscription_end:
        days_left = (user.subscription_end - datetime.now()).days
        sub_info = f"Expires: {user.subscription_end.strftime('%Y-%m-%d')} ({days_left} days left)"
    else:
        sub_info = "No active subscription"
    
    # Get user's groups
    groups = await db.get_user_groups(message.from_user.id)
    group_list = "\n".join([f"• {g.group_name} ({'Active' if g.is_active else 'Inactive'})" 
                           for g in groups]) if groups else "No authorized groups"
    
    status_text = f"""
📊 <b>Your Status</b>

<b>Subscription:</b> {sub_status}
{sub_info}

<b>Authorized Groups:</b>
{group_list}

<b>Bot Version:</b> 1.0.0
"""
    await message.answer(status_text, parse_mode="HTML")

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.chat.type == 'private':
        # Show user's groups stats
        groups = await db.get_user_groups(message.from_user.id)
        if not groups:
            await message.answer("❌ You don't have any authorized groups.")
            return
        
        text = "📈 <b>Your Groups Analytics (Last 7 days)</b>\n\n"
        for group in groups:
            stats = await db.get_stats(group.group_id, 7)
            total_msgs = sum(s.message_count for s in stats)
            total_new = sum(s.new_members for s in stats)
            total_spam = sum(s.spam_blocked for s in stats)
            
            text += f"""
<b>{group.group_name}:</b>
• Messages: {total_msgs}
• New Members: {total_new}
• Spam Blocked: {total_spam}
"""
        await message.answer(text, parse_mode="HTML")
    else:
        # Show current group stats
        group = await db.get_group(message.chat.id)
        if not group:
            await message.answer("❌ This group is not activated. Use /activate first.")
            return
        
        # Verify user is owner or admin
        if group.owner_id != message.from_user.id and not await is_admin(message.from_user.id):
            await message.answer("❌ Only group owner can view stats.")
            return
        
        stats = await db.get_stats(message.chat.id, 7)
        
        if not stats:
            await message.answer("📊 No data available yet. Stats appear after 24 hours.")
            return
        
        total_msgs = sum(s.message_count for s in stats)
        total_new = sum(s.new_members for s in stats)
        total_spam = sum(s.spam_blocked for s in stats)
        
        text = f"""
📈 <b>{message.chat.title} - Statistics (Last 7 days)</b>

<b>Total Messages:</b> {total_msgs}
<b>New Members:</b> {total_new}
<b>Spam Blocked:</b> {total_spam}

<b>Daily Breakdown:</b>
"""
        for day in stats[:7]:
            text += f"\n{day.date}: {day.message_count} msgs, {day.new_members} new"
        
        await message.answer(text, parse_mode="HTML")

@dp.message(Command("settings"))
async def cmd_settings(message: Message):
    if message.chat.type == 'private':
        await message.answer("❌ This command only works in groups!")
        return
    
    group = await db.get_group(message.chat.id)
    if not group:
        await message.answer("❌ Group not activated. Use /activate first.")
        return
    
    if group.owner_id != message.from_user.id and not await is_admin(message.from_user.id):
        await message.answer("❌ Only group owner can change settings.")
        return
    
    settings = group.settings
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{'✅' if settings.get('spam_protection') else '❌'} Anti-Spam", 
            callback_data=f"toggle_spam:{message.chat.id}"
        )],
        [InlineKeyboardButton(
            text=f"{'✅' if settings.get('welcome_message') else '❌'} Welcome Msg", 
            callback_data=f"toggle_welcome:{message.chat.id}"
        )],
        [InlineKeyboardButton(
            text=f"{'✅' if settings.get('auto_mute') else '❌'} Auto-Mute", 
            callback_data=f"toggle_mute:{message.chat.id}"
        )],
        [InlineKeyboardButton(text="🔙 Close", callback_data="close_settings")]
    ])
    
    await message.answer(
        "⚙️ <b>Group Settings</b>\n\nClick to toggle features:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

# Admin commands
@dp.message(Command("addsub"))
async def cmd_addsub(message: Message):
    if not await is_admin(message.from_user.id):
        return
    
    try:
        args = message.text.split()
        if len(args) < 2:
            await message.answer("Usage: /addsub <user_id> [days]")
            return
        
        user_id = int(args[1])
        days = int(args[2]) if len(args) > 2 else 30
        
        await db.activate_subscription(user_id, days)
        await message.answer(f"✅ Subscription activated for user {user_id} ({days} days)")
        
        # Notify user
        try:
            await bot.send_message(
                user_id, 
                f"🎉 <b>Subscription Activated!</b>\n\n"
                f"Your subscription is now active for {days} days.\n"
                f"You can now use /activate in your groups.",
                parse_mode="HTML"
            )
        except:
            pass
            
    except ValueError:
        await message.answer("❌ Invalid user ID")

@dp.message(Command("removesub"))
async def cmd_removesub(message: Message):
    if not await is_admin(message.from_user.id):
        return
    
    try:
        args = message.text.split()
        if len(args) < 2:
            await message.answer("Usage: /removesub <user_id>")
            return
        
        user_id = int(args[1])
        
        async with db.get_db() as database:
            await database.execute(
                'UPDATE users SET is_paid = 0, subscription_end = NULL WHERE user_id = ?',
                (user_id,)
            )
            await database.commit()
        
        await message.answer(f"✅ Subscription removed for user {user_id}")
        
    except ValueError:
        await message.answer("❌ Invalid user ID")

# Message handlers for groups
@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def handle_group_message(message: Message):
    # Skip if group not activated
    group = await db.get_group(message.chat.id)
    if not group or not group.is_active:
        return
    
    settings = group.settings
    user_id = message.from_user.id
    
    # Log message for analytics
    await db.log_message(message.chat.id)
    
    # Check spam protection
    if settings.get('spam_protection', True):
        is_spam = await db.check_spam(user_id, message.chat.id, config.SPAM_THRESHOLD)
        
        if is_spam:
            await db.log_spam_blocked(message.chat.id)
            
            try:
                await message.delete()
                
                if settings.get('auto_mute', True):
                    until_date = datetime.now() + timedelta(seconds=config.MUTE_DURATION)
                    await bot.restrict_chat_member(
                        message.chat.id,
                        user_id,
                        until_date=until_date,
                        can_send_messages=False
                    )
                    await message.answer(
                        f"🚫 <b>Spam detected!</b>\n"
                        f"User {message.from_user.mention_html()} has been muted for 1 hour.",
                        parse_mode="HTML"
                    )
                else:
                    await message.answer("🚫 Spam message deleted.")
                    
            except TelegramAPIError as e:
                logger.error(f"Failed to handle spam: {e}")
            
            return
    
    # Check for links (if enabled)
    if settings.get('spam_protection', True):
        text = message.text or message.caption or ""
        
        # Skip for admins
        try:
            member = await bot.get_chat_member(message.chat.id, user_id)
            if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
                return
        except:
            pass
        
        # Check for spam content
        is_spam, reason = spam_detector.is_spam(text)
        
        if is_spam or spam_detector.contains_link(text):
            try:
                await message.delete()
                await db.log_spam_blocked(message.chat.id)
                await message.answer(
                    f"🚫 <b>Blocked:</b> {reason}\n"
                    f"Message from {message.from_user.mention_html()} removed.",
                    parse_mode="HTML"
                )
                return
            except TelegramAPIError:
                pass

# Welcome new members
@dp.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def on_new_member(event: ChatMemberUpdated):
    group = await db.get_group(event.chat.id)
    if not group or not group.is_active:
        return
    
    settings = group.settings
    if not settings.get('welcome_message', True):
        return
    
    new_member = event.new_chat_member.user
    
    # Skip bots
    if new_member.is_bot:
        return
    
    # Log new member
    await db.log_new_member(event.chat.id)
    
    welcome_text = f"""
👋 <b>Welcome, {new_member.full_name}!</b>

Welcome to {event.chat.title}!

Please read the rules and enjoy your stay.
"""
    
    try:
        await bot.send_message(event.chat.id, welcome_text, parse_mode="HTML")
    except TelegramAPIError:
        pass

# Callback handlers
@dp.callback_query(F.data.startswith("toggle_"))
async def process_toggle(callback: types.CallbackQuery):
    action, group_id = callback.data.split(":")
    group_id = int(group_id)
    
    group = await db.get_group(group_id)
    if not group:
        await callback.answer("Group not found!", show_alert=True)
        return
    
    if group.owner_id != callback.from_user.id and not await is_admin(callback.from_user.id):
        await callback.answer("Not authorized!", show_alert=True)
        return
    
    settings = group.settings
    
    if "spam" in action:
        settings['spam_protection'] = not settings.get('spam_protection', True)
    elif "welcome" in action:
        settings['welcome_message'] = not settings.get('welcome_message', True)
    elif "mute" in action:
        settings['auto_mute'] = not settings.get('auto_mute', True)
    
    await db.update_group_settings(group_id, settings)
    await callback.answer("Setting updated!")
    
    # Update keyboard
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{'✅' if settings.get('spam_protection') else '❌'} Anti-Spam", 
            callback_data=f"toggle_spam:{group_id}"
        )],
        [InlineKeyboardButton(
            text=f"{'✅' if settings.get('welcome_message') else '❌'} Welcome Msg", 
            callback_data=f"toggle_welcome:{group_id}"
        )],
        [InlineKeyboardButton(
            text=f"{'✅' if settings.get('auto_mute') else '❌'} Auto-Mute", 
            callback_data=f"toggle_mute:{group_id}"
        )],
        [InlineKeyboardButton(text="🔙 Close", callback_data="close_settings")]
    ])
    
    await callback.message.edit_reply_markup(reply_markup=keyboard)

@dp.callback_query(F.data == "close_settings")
async def close_settings(callback: types.CallbackQuery):
    await callback.message.delete()

@dp.callback_query(F.data == "subscribe")
async def process_subscribe(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "💳 <b>Subscription Information</b>\n\n"
        f"Price: ${config.SUBSCRIPTION_PRICE}/month\n"
        f"Duration: {config.SUBSCRIPTION_DAYS} days\n\n"
        "To purchase, contact the administrator.",
        parse_mode="HTML"
    )

# Error handler
@dp.errors()
async def error_handler(event: types.ErrorEvent):
    logger.error(f"Update {event.update.update_id} caused error: {event.exception}")
    return True

async def main():
    # Initialize database
    await db.init()
    logger.info("Database initialized")
    
    # Start polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
