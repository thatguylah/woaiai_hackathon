import os
import json
import base64
import io
import numpy as np
import cv2
import torch
from PIL import Image
import boto3
from skimage.metrics import structural_similarity
from diffusers import StableDiffusionInpaintPipeline
import requests

from dotenv import dotenv_values

config = dotenv_values(".env")
AWS_ACCESS_KEY = config["AWS_ACCESS_KEY"]
AWS_SECRET_ACCESS_KEY = config["AWS_SECRET_ACCESS_KEY"]
S3_BUCKET = config["BUCKET_NAME"]
TELEBOT_API_URL = config["TELEBOT_API_TOKEN"]
TELEBOT_API_URL = config[
    "TELEBOT_DEV_API_TOKEN"
]  ## To be commented out when deploying to production
s3 = boto3.client(
    "s3", aws_access_key_id=AWS_ACCESS_KEY, aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)


def get_mask(image1_pil, image2_pil):
    # Convert to cv2 format
    image1_np = np.array(image1_pil)
    image2_np = np.array(image2_pil)
    image1_bgr = cv2.cvtColor(image1_np, cv2.COLOR_RGB2BGR)
    image2_bgr = cv2.cvtColor(image2_np, cv2.COLOR_RGB2BGR)

    # # METHOD 1: Compare the two images and get the difference mask
    # diff = cv2.absdiff(image1_bgr, image2_bgr)
    # diff_mask = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    # th = 15
    # imask =  diff_mask>th
    # mask = np.zeros_like(image1_bgr, np.uint8)
    # mask[imask] = 255

    # # METHOD 2: Use structural similarity and contour regions
    # taken from: https://stackoverflow.com/questions/56183201/detect-and-visualize-differences-between-two-images-with-opencv-python
    before_gray = cv2.cvtColor(image1_bgr, cv2.COLOR_BGR2GRAY)
    after_gray = cv2.cvtColor(image2_bgr, cv2.COLOR_BGR2GRAY)
    (score, diff) = structural_similarity(
        before_gray, after_gray, full=True
    )  # Compute SSIM between the two images
    diff = (diff * 255).astype("uint8")
    diff_box = cv2.merge([diff, diff, diff])
    # Threshold the difference image, followed by finding contours to obtain the regions of the two input images that differ
    thresh = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    contours = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = contours[0] if len(contours) == 2 else contours[1]
    mask = np.zeros(image1_bgr.shape, dtype="uint8")
    for c in contours:
        area = cv2.contourArea(c)
        if area > 10:  # minimum contour area
            cv2.drawContours(mask, [c], 0, (255, 255, 255), -1)

    # convert mask back to PIL
    mask_pil = Image.fromarray(mask)
    mask_pil.save("pre_mask.png")
    return mask_pil


def remove(original, masked, username, chat_id, date_received):
    mask = get_mask(original, masked)

    pipe = StableDiffusionInpaintPipeline.from_pretrained(
        # "stabilityai/stable-diffusion-2-inpainting",
        "./stable-diffusion-2-inpainting",
        # torch_dtype=torch.float16,
    )
    device = "cuda" if torch.cuda.is_available() else "cpu"
    pipe.to(device)
    # image and mask_image should be PIL images.
    # The mask structure is white for inpainting and black for keeping as is
    image = pipe(prompt="", image=original, mask_image=mask).images[0]
    image.save("./removed.png")
    # save_image_s3(image,username,chat_id,date_received)

    # in_mem_file = io.BytesIO()
    # image.save(in_mem_file, format=image.format)
    # in_mem_file.seek(0)

    try:
        response = s3.upload_file(
            image, S3_BUCKET, f"/output/{username}/{date_received}-{chat_id}-result.png"
        )
    except Exception as e:
        print("error in s3 upload", e)

    return image


def get_image_s3(bucket, key):
    file_byte_string = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    image = Image.open(io.BytesIO(file_byte_string))

    return image


# def save_image_s3(pil_image,username,chat_id,date_received):
#     in_mem_file = io.BytesIO()
#     pil_image.save(in_mem_file, format=pil_image.format)
#     in_mem_file.seek(0)

#     try:
#         response = s3.upload_file(in_mem_file, S3_BUCKET, f"/output/{username}/{date_received}-{chat_id}-result.png")
#     except Exception as e:
#         print("error in s3 upload", e)


def handler(event, context):
    # Print out events
    # event = json.loads(event)
    print(event)

    # Purge Message from queue

    # Access the message from the event
    original_key = event["base_image_s3_key"]
    masked_key = event["mask_image_s3_key"]
    chat_id = event["message"]["chat"]["id"]
    date_received = event["message"]["date"]

    if "username" in event["message"]["chat"]:
        username = event["message"]["chat"]["username"]
    else:
        username = event["message"]["chat"]["first_name"]

    # Retrieve images from s3
    original = get_image_s3(S3_BUCKET, original_key)
    masked = get_image_s3(S3_BUCKET, masked_key)
    print("retrieved images from s3")

    # Run remove function
    generated_image = remove(original, masked, username, chat_id, date_received)

    # Send image to user
    url = f"${TELEBOT_API_URL}/sendPhoto"

    payload = {
        "photo": "./removed.png",
        "chat_id": chat_id,
        "caption": f"Here is your masked image! We received the masked image on {date_received}",
        "disable_notification": False,
        "reply_to_message_id": None,
    }
    headers = {"accept": "application/json", "content-type": "application/json"}

    response = requests.post(url, json=payload, headers=headers)

    return {"statusCode": 200, "body": f"${response.text}"}


# if __name__ == "__main__":
#     event = {
#         "update_id": 703295117,
#         "message": {
#             "chat": {"id": 332090205, "type": "private", "first_name": "cyk"},
#             "group_chat_created": False,
#             "message_id": 1073,
#             "delete_chat_photo": False,
#             "date": 1687922518,
#             "supergroup_chat_created": False,
#             "photo": [
#                 {
#                     "width": 90,
#                     "height": 14,
#                     "file_id": "AgACAgUAAxkBAAIEMWSbp1bvrfxH62zZro-ytsb3DlKQAALgujEbudrYVPjw6jZUQy41AQADAgADcwADLwQ",
#                     "file_size": 629,
#                     "file_unique_id": "AQAD4LoxG7na2FR4",
#                 },
#                 {
#                     "width": 320,
#                     "height": 51,
#                     "file_id": "AgACAgUAAxkBAAIEMWSbp1bvrfxH62zZro-ytsb3DlKQAALgujEbudrYVPjw6jZUQy41AQADAgADbQADLwQ",
#                     "file_size": 6469,
#                     "file_unique_id": "AQAD4LoxG7na2FRy",
#                 },
#                 {
#                     "width": 936,
#                     "height": 150,
#                     "file_id": "AgACAgUAAxkBAAIEMWSbp1bvrfxH62zZro-ytsb3DlKQAALgujEbudrYVPjw6jZUQy41AQADAgADeQADLwQ",
#                     "file_size": 23515,
#                     "file_unique_id": "AQAD4LoxG7na2FR-",
#                 },
#                 {
#                     "width": 800,
#                     "height": 128,
#                     "file_id": "AgACAgUAAxkBAAIEMWSbp1bvrfxH62zZro-ytsb3DlKQAALgujEbudrYVPjw6jZUQy41AQADAgADeAADLwQ",
#                     "file_size": 24964,
#                     "file_unique_id": "AQAD4LoxG7na2FR9",
#                 },
#             ],
#             "channel_chat_created": False,
#             "from": {
#                 "is_bot": False,
#                 "first_name": "cyk",
#                 "id": 332090205,
#                 "language_code": "en",
#             },
#         },
#         "base_image_s3_key": "input/base-image/cyk/AgACAgUAAxkBAAIEL2Sbp0qItOUWBoYpwar3WRRItZ7zAALcujEbudrYVJpIxU9TtzNvAQADAgADeQADLwQ20230628112146.jpg",
#         "mask_image_s3_key": "input/mask-image/cyk/AgACAgUAAxkBAAIEMWSbp1bvrfxH62zZro-ytsb3DlKQAALgujEbudrYVPjw6jZUQy41AQADAgADeAADLwQ20230628112158.jpg",
#     }
#     handler(event=event, context=None)
