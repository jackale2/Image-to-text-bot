import os
import logging
import sqlite3
from datetime import datetime
from google.cloud import vision
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Initialize logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# Global variables
DAILY_LIMIT = 10
DB_PATH = 'user_data.db'

# Load credentials from environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
GOOGLE_APPLICATION_CREDENTIALS = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

if not BOT_TOKEN or not GOOGLE_APPLICATION_CREDENTIALS:
    raise ValueError("Missing BOT_TOKEN or GOOGLE_APPLICATION_CREDENTIALS environment variable")

# Initialize SQLite database
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        last_access DATE,
        image_count INTEGER
    )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_user_data(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT last_access, image_count FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result

def update_user_data(user_id, image_count, last_access):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO users (user_id, last_access, image_count) 
    VALUES (?, ?, ?)
    ON CONFLICT(user_id) DO UPDATE SET last_access = excluded.last_access, image_count = excluded.image_count
    ''', (user_id, last_access, image_count))
    conn.commit()
    conn.close()

def reset_daily_count_if_needed(user_id):
    today = datetime.now().date()
    user_data = get_user_data(user_id)
    if user_data:
        last_access, image_count = user_data
        if datetime.strptime(last_access, '%Y-%m-%d').date() < today:
            update_user_data(user_id, 0, today)
    else:
        update_user_data(user_id, 0, today)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    reset_daily_count_if_needed(user_id)
    await update.message.reply_text(
        'Hello! 👋\n\n'
        'I am an image to text bot. You can send up to 10 images per day for conversion to text.\n\n'
        'If you want more images, you can purchase VIP. Please contact me at @Yourusername for more details. 📩'
    )

async def process_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    reset_daily_count_if_needed(user_id)

    user_data = get_user_data(user_id)
    image_count = user_data[1] if user_data else 0

    if image_count >= DAILY_LIMIT:
        await update.message.reply_text('You have reached the daily limit of 10 images.')
        return

    # Process the image with Google Vision API
    client = vision.ImageAnnotatorClient()
    photo_file = await update.message.photo[-1].get_file()
    photo_path = os.path.join('/tmp', f'{user_id}_{photo_file.file_id}.jpg')
    await photo_file.download(photo_path)

    with open(photo_path, 'rb') as image_file:
        content = image_file.read()
    image = vision.Image(content=content)
    response = client.label_detection(image=image)
    labels = response.label_annotations

    label_descriptions = [label.description for label in labels]
    labels_text = '\n'.join(label_descriptions)

    # Increment the user's image count
    update_user_data(user_id, image_count + 1, datetime.now().date())

    await update.message.reply_text(f'Image processed successfully! Description:\n{labels_text}')

async def user_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    count = cursor.fetchone()[0]
    conn.close()
    await update.message.reply_text(f'Total number of users: {count}')

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("user_count", user_count))
    application.add_handler(MessageHandler(filters.PHOTO, process_image))

    application.run_polling()

if __name__ == '__main__':
    main()
