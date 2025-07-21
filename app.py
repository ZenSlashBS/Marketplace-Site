# app.py
import os
import threading
import sqlite3
from flask import Flask, render_template, send_from_directory, request, url_for
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler, CallbackContext
import logging
import uuid

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Database setup
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS tools
                 (id INTEGER PRIMARY KEY, name TEXT, info TEXT, image_path TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS creators
                 (id INTEGER PRIMARY KEY, name TEXT, image_path TEXT)''')
    conn.commit()
    conn.close()

init_db()

# Telegram Bot Setup
TOKEN = '7686127373:AAFgxwOcOYG_veGOMxrby6Bmr62PndlFW3I'
ADMIN_ID = 7067323341

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# States for ConversationHandler
MAIN_MENU, UPLOAD_TOOL, UPLOAD_CREATOR, ADD_TOOL_IMAGE, ADD_TOOL_NAME, ADD_TOOL_INFO, EDIT_TOOL_IMAGE, EDIT_TOOL_NAME, EDIT_TOOL_INFO, ADD_CREATOR_IMAGE, ADD_CREATOR_NAME, EDIT_CREATOR_IMAGE, EDIT_CREATOR_NAME = range(13)

async def start(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this bot.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("Upload Tools", callback_data='upload_tools')],
        [InlineKeyboardButton("Upload Creators", callback_data='upload_creators')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Welcome Admin! Choose an option:", reply_markup=reply_markup)
    return MAIN_MENU

async def button(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == 'upload_tools':
        return await show_tools(update, context)
    elif query.data == 'upload_creators':
        return await show_creators(update, context)
    elif query.data.startswith('tool_'):
        tool_id = int(query.data.split('_')[1])
        context.user_data['current_tool_id'] = tool_id
        return await show_tool_details(update, context, tool_id)
    elif query.data == 'add_tool':
        await query.edit_message_text("Please send the image for the new tool.")
        return ADD_TOOL_IMAGE
    elif query.data == 'edit_tool':
        await query.edit_message_text("Send new image or type 'skip' to keep current.")
        return EDIT_TOOL_IMAGE
    elif query.data == 'back_tools':
        return await show_tools(update, context)
    elif query.data.startswith('creator_'):
        creator_id = int(query.data.split('_')[1])
        context.user_data['current_creator_id'] = creator_id
        return await show_creator_details(update, context, creator_id)
    elif query.data == 'add_creator':
        await query.edit_message_text("Please send the image for the new creator.")
        return ADD_CREATOR_IMAGE
    elif query.data == 'edit_creator':
        await query.edit_message_text("Send new image or type 'skip' to keep current.")
        return EDIT_CREATOR_IMAGE
    elif query.data == 'back_creators':
        return await show_creators(update, context)

async def show_tools(update: Update, context: CallbackContext) -> int:
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT id, name FROM tools")
    tools = c.fetchall()
    conn.close()

    keyboard = [[InlineKeyboardButton(name, callback_data=f'tool_{id}')] for id, name in tools]
    keyboard.append([InlineKeyboardButton("+ Add New Tool", callback_data='add_tool')])

    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text("Select a tool to edit or add new:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Select a tool to edit or add new:", reply_markup=reply_markup)
    return UPLOAD_TOOL

async def show_tool_details(update: Update, context: CallbackContext, tool_id: int) -> int:
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT name, info, image_path FROM tools WHERE id=?", (tool_id,))
    name, info, image_path = c.fetchone()
    conn.close()

    caption = f"Name: {name}\nInfo: {info}"
    if image_path:
        await update.callback_query.message.reply_photo(photo=open(image_path, 'rb'), caption=caption)
    else:
        await update.callback_query.message.reply_text(caption)

    keyboard = [
        [InlineKeyboardButton("Edit", callback_data='edit_tool')],
        [InlineKeyboardButton("Back", callback_data='back_tools')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.message.reply_text("Actions:", reply_markup=reply_markup)
    return UPLOAD_TOOL

async def add_tool_image(update: Update, context: CallbackContext) -> int:
    if update.message.photo:
        photo = update.message.photo[-1].get_file()
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}.jpg")
        await photo.download_to_drive(file_path)
        context.user_data['new_tool_image'] = file_path
        await update.message.reply_text("Image received. Now enter the name:")
        return ADD_TOOL_NAME
    else:
        await update.message.reply_text("Please send a photo.")
        return ADD_TOOL_IMAGE

async def add_tool_name(update: Update, context: CallbackContext) -> int:
    context.user_data['new_tool_name'] = update.message.text
    await update.message.reply_text("Enter the info:")
    return ADD_TOOL_INFO

async def add_tool_info(update: Update, context: CallbackContext) -> int:
    info = update.message.text
    image_path = context.user_data.get('new_tool_image')
    name = context.user_data.get('new_tool_name')

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("INSERT INTO tools (name, info, image_path) VALUES (?, ?, ?)", (name, info, image_path))
    conn.commit()
    conn.close()

    await update.message.reply_text("Tool added successfully!")
    del context.user_data['new_tool_image']
    del context.user_data['new_tool_name']
    return await show_tools(update, context)

async def edit_tool_image(update: Update, context: CallbackContext) -> int:
    tool_id = context.user_data['current_tool_id']
    if update.message.photo:
        photo = update.message.photo[-1].get_file()
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}.jpg")
        await photo.download_to_drive(file_path)
        context.user_data['edit_image'] = file_path
    elif update.message.text.lower() == 'skip':
        context.user_data['edit_image'] = None
    else:
        await update.message.reply_text("Please send a photo or type 'skip'.")
        return EDIT_TOOL_IMAGE

    await update.message.reply_text("Enter new name or 'skip' to keep current:")
    return EDIT_TOOL_NAME

async def edit_tool_name(update: Update, context: CallbackContext) -> int:
    text = update.message.text
    if text.lower() == 'skip':
        context.user_data['edit_name'] = None
    else:
        context.user_data['edit_name'] = text

    await update.message.reply_text("Enter new info or 'skip' to keep current:")
    return EDIT_TOOL_INFO

async def edit_tool_info(update: Update, context: CallbackContext) -> int:
    text = update.message.text
    edit_info = None if text.lower() == 'skip' else text

    tool_id = context.user_data['current_tool_id']
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT name, info, image_path FROM tools WHERE id=?", (tool_id,))
    old_name, old_info, old_image = c.fetchone()

    new_name = context.user_data.get('edit_name') or old_name
    new_info = edit_info or old_info
    new_image = context.user_data.get('edit_image') or old_image

    c.execute("UPDATE tools SET name=?, info=?, image_path=? WHERE id=?", (new_name, new_info, new_image, tool_id))
    conn.commit()
    conn.close()

    await update.message.reply_text("Tool updated successfully!")
    context.user_data.pop('edit_image', None)
    context.user_data.pop('edit_name', None)
    return await show_tools(update, context)

async def show_creators(update: Update, context: CallbackContext) -> int:
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT id, name FROM creators")
    creators = c.fetchall()
    conn.close()

    keyboard = [[InlineKeyboardButton(name, callback_data=f'creator_{id}')] for id, name in creators]
    keyboard.append([InlineKeyboardButton("+ Add New Creator", callback_data='add_creator')])

    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text("Select a creator to edit or add new:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Select a creator to edit or add new:", reply_markup=reply_markup)
    return UPLOAD_CREATOR

async def show_creator_details(update: Update, context: CallbackContext, creator_id: int) -> int:
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT name, image_path FROM creators WHERE id=?", (creator_id,))
    name, image_path = c.fetchone()
    conn.close()

    caption = f"Name: {name}"
    if image_path:
        await update.callback_query.message.reply_photo(photo=open(image_path, 'rb'), caption=caption)
    else:
        await update.callback_query.message.reply_text(caption)

    keyboard = [
        [InlineKeyboardButton("Edit", callback_data='edit_creator')],
        [InlineKeyboardButton("Back", callback_data='back_creators')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.message.reply_text("Actions:", reply_markup=reply_markup)
    return UPLOAD_CREATOR

async def add_creator_image(update: Update, context: CallbackContext) -> int:
    if update.message.photo:
        photo = update.message.photo[-1].get_file()
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}.jpg")
        await photo.download_to_drive(file_path)
        context.user_data['new_creator_image'] = file_path
        await update.message.reply_text("Image received. Now enter the name:")
        return ADD_CREATOR_NAME
    else:
        await update.message.reply_text("Please send a photo.")
        return ADD_CREATOR_IMAGE

async def add_creator_name(update: Update, context: CallbackContext) -> int:
    name = update.message.text
    image_path = context.user_data.get('new_creator_image')

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("INSERT INTO creators (name, image_path) VALUES (?, ?)", (name, image_path))
    conn.commit()
    conn.close()

    await update.message.reply_text("Creator added successfully!")
    del context.user_data['new_creator_image']
    return await show_creators(update, context)

async def edit_creator_image(update: Update, context: CallbackContext) -> int:
    creator_id = context.user_data['current_creator_id']
    if update.message.photo:
        photo = update.message.photo[-1].get_file()
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}.jpg")
        await photo.download_to_drive(file_path)
        context.user_data['edit_image'] = file_path
    elif update.message.text.lower() == 'skip':
        context.user_data['edit_image'] = None
    else:
        await update.message.reply_text("Please send a photo or type 'skip'.")
        return EDIT_CREATOR_IMAGE

    await update.message.reply_text("Enter new name or 'skip' to keep current:")
    return EDIT_CREATOR_NAME

async def edit_creator_name(update: Update, context: CallbackContext) -> int:
    text = update.message.text
    edit_name = None if text.lower() == 'skip' else text

    creator_id = context.user_data['current_creator_id']
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT name, image_path FROM creators WHERE id=?", (creator_id,))
    old_name, old_image = c.fetchone()

    new_name = edit_name or old_name
    new_image = context.user_data.get('edit_image') or old_image

    c.execute("UPDATE creators SET name=?, image_path=? WHERE id=?", (new_name, new_image, creator_id))
    conn.commit()
    conn.close()

    await update.message.reply_text("Creator updated successfully!")
    context.user_data.pop('edit_image', None)
    return await show_creators(update, context)

def run_bot():
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            MAIN_MENU: [CallbackQueryHandler(button)],
            UPLOAD_TOOL: [CallbackQueryHandler(button)],
            UPLOAD_CREATOR: [CallbackQueryHandler(button)],
            ADD_TOOL_IMAGE: [MessageHandler(filters.PHOTO, add_tool_image)],
            ADD_TOOL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_tool_name)],
            ADD_TOOL_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_tool_info)],
            EDIT_TOOL_IMAGE: [MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, edit_tool_image)],
            EDIT_TOOL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_tool_name)],
            EDIT_TOOL_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_tool_info)],
            ADD_CREATOR_IMAGE: [MessageHandler(filters.PHOTO, add_creator_image)],
            ADD_CREATOR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_creator_name)],
            EDIT_CREATOR_IMAGE: [MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, edit_creator_image)],
            EDIT_CREATOR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_creator_name)],
        },
        fallbacks=[],
    )

    application.add_handler(conv_handler)
    application.run_polling()

# Flask routes
@app.route('/')
def index():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT name, info, image_path FROM tools")
    tools = c.fetchall()
    c.execute("SELECT name, image_path FROM creators")
    creators = c.fetchall()
    conn.close()

    hero_image = 'https://iili.io/FwOJIY7.jpg'
    default_creator = {'name': 'Aarav GF', 'image_path': hero_image}

    return render_template('index.html', tools=tools, creators=creators, hero_image=hero_image, default_creator=default_creator)

@app.route('/static/uploads/<filename>')
def uploads(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    port = int(os.environ.get('PORT', 80))
    app.run(host='0.0.0.0', port=port, debug=False)
