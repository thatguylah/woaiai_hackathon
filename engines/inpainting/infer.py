import os
import base64
import numpy as np
import cv2 
from PIL import Image
import boto3
import urllib
from botocore.exceptions import ClientError
import time
from io import BytesIO
import json
import requests

from skimage.metrics import structural_similarity

s3 = boto3.client("s3")
S3_BUCKET = os.environ['S3_BUCKET']
SM_ENDPONT = os.environ['SM_ENDPOINT']
TELEBOT_TOKEN = os.environ['TELEBOT_TOKEN']

def get_mask(image1_pil, image2_pil):

    # Convert to cv2 format
    image1_np = np.array(image1_pil)
    image2_np = np.array(image2_pil)
    image1_bgr = cv2.cvtColor(image1_np, cv2.COLOR_RGB2BGR)
    image2_bgr = cv2.cvtColor(image2_np, cv2.COLOR_RGB2BGR)

    # # METHOD 2: Use structural similarity and contour regions
    # taken from: https://stackoverflow.com/questions/56183201/detect-and-visualize-differences-between-two-images-with-opencv-python
    before_gray = cv2.cvtColor(image1_bgr, cv2.COLOR_BGR2GRAY)
    after_gray = cv2.cvtColor(image2_bgr, cv2.COLOR_BGR2GRAY)
    (score, diff) = structural_similarity(before_gray, after_gray, full=True) # Compute SSIM between the two images
    diff = (diff * 255).astype("uint8")
    diff_box = cv2.merge([diff, diff, diff])
    # Threshold the difference image, followed by finding contours to obtain the regions of the two input images that differ
    thresh = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    contours = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = contours[0] if len(contours) == 2 else contours[1]
    mask = np.zeros(image1_bgr.shape, dtype='uint8')
    for c in contours:
        area = cv2.contourArea(c)
        if area > 10: # minimum contour area
            cv2.drawContours(mask, [c], 0, (255,255,255), -1)

    # convert mask back to PIL
    mask_pil = Image.fromarray(mask)

    return mask_pil

def get_image_s3(bucket, key):
    file_byte_string = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    image = Image.open(BytesIO(file_byte_string))

    return image

def resize_image(pil_image):
    max_width = 500
    max_height = 800
    im_width = pil_image.size[0]
    im_height = pil_image.size[1]
    if im_width <= max_width and im_height <= max_height: 
        return pil_image
    else:     
        if im_width > max_width:
            wpercent = (max_width/float(im_width))
            hsize = int((float(im_height)*float(wpercent)))
            return pil_image.resize((max_width, hsize), Image.ANTIALIAS)
        else:
            hpercent = (max_height/float(im_height))
            wsize = int((float(im_width)*float(hpercent)))
            return pil_image.resize((wsize, max_height), Image.ANTIALIAS)

def pil2bytes(pil_image):
    buffered = BytesIO()
    pil_image.save(buffered, format="JPEG")
    img_bytes = base64.b64encode(buffered.getvalue()).decode()
    
    return img_bytes

        
def get_output(success_location, failure_location):
    output_url = urllib.parse.urlparse(success_location)
    failure_url = urllib.parse.urlparse(failure_location)
    while True:
        try:
            s3_output_obj = s3.get_object(Bucket=output_url.netloc, Key=output_url.path[1:])
            return s3_output_obj["Body"].read().decode("utf-8")
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                time.sleep(10)
                try:
                    s3_failure_obj = s3.get_object(Bucket=failure_url.netloc, Key=failure_url.path[1:])
                    error_output = s3_failure_obj["Body"].read().decode("utf-8")
                    raise Exception("Failure output detected in invoking async endpoint. Check S3 failure location", failure_location)
                except ClientError as e:
                    if e.response["Error"]["Code"] == "NoSuchKey":
                        print("Polling S3 bucket for Sagemaker output..")
                        continue
                    else: 
                        print("Error in reading error output in S3", e)
            raise

def post_request(s3_request_payload_key, endpoint_name):
    boto_session = boto3.session.Session()
    sm_runtime = boto_session.client("sagemaker-runtime")

    resp = sm_runtime.invoke_endpoint_async(
            EndpointName=endpoint_name, InputLocation=f"s3://{S3_BUCKET}/{s3_request_payload_key}", ContentType='application/json;jpeg'
        )
    print(f"Response from Sagemaker invoke_endpoint_async: {resp}")
    success_output_location = resp["OutputLocation"]
    failure_output_location = resp["FailureLocation"]

    return success_output_location, failure_output_location


def remove(original_key, masked_key, results_key_prefix):
    print("Getting S3 images")

    original = get_image_s3(S3_BUCKET, original_key)
    masked = get_image_s3(S3_BUCKET, masked_key)
    original = resize_image(original)
    masked = resize_image(masked)

    print("Getting mask")
    mask = get_mask(original, masked)
    
    payload = {
        "prompt": "",
        "image": pil2bytes(original),
        "mask_image": pil2bytes(mask),
        "num_inference_steps": 50,
        "guidance_scale": 7.5,
        "seed": 0
    }

    # put payload in s3 
    request_payload_key = f"{results_key_prefix}/payload.json"
    s3_response = s3.put_object(
        Body=json.dumps(payload).encode("utf-8"),
        Bucket=S3_BUCKET,
        Key=request_payload_key,
        ContentType='application/json'
    )
    print(f"Response from S3 payload upload: {s3_response}")

    # post to sagemaker endpoint
    success_location, failure_location = post_request(request_payload_key, SM_ENDPONT)
    output = get_output(success_location, failure_location)
    generated_images = json.loads(output)["generated_images"]
    
    return generated_images[0] # return only 1 image


def save_image_s3(image_list, key_prefix):
    np_image = (np.array(image_list)).astype(np.uint8)
    img = Image.fromarray(np_image)

    in_mem_file = BytesIO()
    img.save(in_mem_file, format='jpeg')
    in_mem_file.seek(0)
    response = s3.upload_fileobj(in_mem_file, S3_BUCKET, f"{key_prefix}/result.jpg")

    return response

def send_photo_telebot(image_list, chat_id): 
    np_image = (np.array(image_list)).astype(np.uint8)
    img = Image.fromarray(np_image)
    in_mem_file = BytesIO()
    img.save(in_mem_file, format='jpeg')
    in_mem_file.seek(0)

    params = {'chat_id': chat_id}
    files = {'photo': in_mem_file}
    api_url = f"https://api.telegram.org/bot{TELEBOT_TOKEN}/sendPhoto"
    resp = requests.post(api_url, params, files=files)
    return resp

def send_message_telebot(message, chat_id):
    params = {'chat_id': chat_id, 'text': message}
    api_url = f"https://api.telegram.org/bot{TELEBOT_TOKEN}/sendMessage"
    resp = requests.post(api_url, params)
    return resp


def handler(event, context):
    print("Received event", event)
    for record in event["Records"]:
        payload = json.loads(record["body"])
        print("Received queue msg", payload)
        base_key = payload["base_image_s3_key"]
        masked_key = payload["mask_image_s3_key"]
        base_image_basename = base_key.split("/")[-1].split(".")[0]
        results_key_prefix = f"output/{base_image_basename}"

        try:
            image = remove(base_key, masked_key, results_key_prefix)
            print("Generated removal image")
        except ValueError as e: 
            if str(e) == "Input images must have the same dimensions.":
                tele_message = "Sorry, your job has failed as both images must be of the same dimensions. We encourage you to use Telegram's built-in brush tool to generate masked images. This conversation is over now, please type /outpainting to start a new one. Or type /start for a guided workflow."
                telebot_text_response = send_message_telebot(tele_message, payload["message"]["chat"]["id"])
                return {
                    'statusCode': 501,
                    'body': json.dumps('Input images do not have same dimensions.')
                }
            else: 
                raise Exception(e)

        # save_response = save_image_s3(image, results_key_prefix)
        # print("Done saving s3 result")

        telebot_response = send_photo_telebot(image, payload["message"]["chat"]["id"])

        return {
            'statusCode': 200,
            'body': json.dumps('Image generated')
        }

        

