# pylint: disable=unused-argument, wrong-import-position
# This program is dedicated to the public domain under the CC0 license.

"""
Simple Bot to reply to Telegram messages.

First, a few handler functions are defined. Then, those functions are passed to
the Application and registered at their respective places.
Then, the bot is started and runs until we press Ctrl-C on the command line.

Usage:
Basic Echobot example, repeats messages.
Press Ctrl-C on the command line or send a signal to the process to stop the
bot.
"""
import boto3
import logging
import json
from dotenv import dotenv_values
import requests
import json
import argparse
from huggingface_hub import InferenceClient
# from flask import Flask
# from flask import request
# from flask import Response

config = dotenv_values(".env")
HF_TOKEN = config['HF_API_KEY']

from telegram import __version__ as TG_VER

try:
    from telegram import __version_info__
except ImportError:
    __version_info__ = (0, 0, 0, 0, 0)  # type: ignore[assignment]

if __version_info__ < (20, 0, 0, "alpha", 1):
    raise RuntimeError(
        f"This example is not compatible with your current PTB version {TG_VER}. To view the "
        f"{TG_VER} version of this example, "
        f"visit https://docs.python-telegram-bot.org/en/v{TG_VER}/examples.html"
    )
from telegram import ForceReply, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Define a few command handlers. These usually take the two arguments update and
# context.
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}!",
        reply_markup=ForceReply(selective=True),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    helpLogger = logging.getLogger("helpProcess")
    update_as_json = json.dumps(update.to_dict())
    helpLogger.info(update_as_json)
    helpLogger.info(update.effective_chat.first_name + " "+ "sent the message of:" + update.message.text)
    await update.message.reply_text("Help!")
    

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Echo the user message."""
    client = InferenceClient(token=HF_TOKEN)
    echoLogger = logging.getLogger("echoProcess")
    update_as_json = json.dumps(update.to_dict())
    echoLogger.info(update_as_json)
    echoLogger.info(update.effective_chat.first_name + " "+ "sent the message of:" + update.message.text)

    image = client.text_to_image(update.message.text)
    image_path="generic_photo.png"
    image.save(image_path)
    
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=open(image_path, "rb"),
        write_timeout=150,
        caption=update.message.text
    )


def main(dev_mode) -> None:
    # Start the bot.
    # Create the Application and pass it your bot's token.
	if dev_mode:
		TELEBOT_TOKEN = config['TELEBOT_DEV_TOKEN']
	else:
		TELEBOT_TOKEN = config['TELEBOT_TOKEN']

	application = Application.builder().token(TELEBOT_TOKEN).build()
	# on different commands - answer in Telegram
	application.add_handler(CommandHandler("start", start))
	application.add_handler(CommandHandler("help", help_command))

	# on non command i.e message - echo the message on Telegram
	application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

	# Run the bot until the user presses Ctrl-C
	application.run_polling()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-DEV", "--dev", action="store_true", help="Run with local Tele API token")
    args = parser.parse_args()

    main(args.dev)