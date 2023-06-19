import telebot

from dotenv import dotenv_values

import requests

config = dotenv_values(".env")

BOT_TOKEN = config['BOT_TOKEN']

bot = telebot.TeleBot(BOT_TOKEN)