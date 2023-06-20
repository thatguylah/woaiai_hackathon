import boto3
import logging
import json
from dotenv import dotenv_values
import requests
import json
import argparse
from huggingface_hub import InferenceClient
import requests
config = dotenv_values(".env")

def main(args):

    if args.dev:
        TELEBOT_TOKEN = config['TELEBOT_DEV_API_TOKEN']
    else:
        TELEBOT_TOKEN = None
    
    send_msg_url = f"{TELEBOT_TOKEN}/sendMessage"
    print(send_msg_url)
    payload = {
        "text": f"{args.msg}",
        "disable_web_page_preview": False,
        "disable_notification": False,
        "reply_to_message_id": None,
        "chat_id": "332090205"
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json"
    }

    response = requests.post(url=send_msg_url, json=payload, headers=headers)

    print(response.text)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-DEV", "--dev", action="store_true", help="Run with local Tele API token")
    parser.add_argument("-M", "--msg", action="store", help="Pass in a string to be sent to user via Tele sendMessage API")
    args = parser.parse_args()

    main(args)