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
REPLICATE_TOKEN = os.environ['REPLICATE_TOKEN']

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

def resize_image(pil_image, width=None, height=None):
    if height and width: 
        return pil_image.resize((width, height), Image.ANTIALIAS)
    else:
        max_width = 640
        max_height = 640
        im_width = pil_image.size[0]
        im_height = pil_image.size[1]
        if im_width <= max_width and im_height <= max_height: 
            return pil_image
        else:
            wpercent = 1
            hpercent = 1     
            if im_width > max_width:
                wpercent = (max_width/float(im_width))
            if im_height > max_height:
                hpercent = (max_height/float(im_height))

            if wpercent < hpercent:
                hsize = int((float(im_height)*float(wpercent)))
                print(f"Resizing height to {hsize}, wpercent={wpercent}, im_width={im_width}, im_height={im_height}.")
                return pil_image.resize((max_width, hsize), Image.ANTIALIAS)
            else:
                wsize = int((float(im_width)*float(hpercent)))
                print(f"Resizing width to {wsize}, hpercent={hpercent}, im_width={im_width}, im_height={im_height}.")
                return pil_image.resize((wsize, max_height), Image.ANTIALIAS)
            

def pil2base64(pil_image):
    buffered = BytesIO()
    pil_image.save(buffered, format="JPEG")
    img_bytes = base64.b64encode(buffered.getvalue()).decode()
    
    return img_bytes


def pil2bytes(pil_image):
    in_mem_file = BytesIO()
    pil_image.save(in_mem_file, format='jpeg')
    in_mem_file.seek(0)
    
    return in_mem_file

        
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


def remove(original_key, masked_key, results_key_prefix, text_prompt):
    print("Getting S3 images")

    original = get_image_s3(S3_BUCKET, original_key)
    masked = get_image_s3(S3_BUCKET, masked_key)
    original = resize_image(original)
    masked = resize_image(masked)

    if original.size !=  masked.size: # sizes still different after masking
        if abs(original.size[0]-masked.size[0]) <= 10 and abs(original.size[1]-masked.size[1]) <= 10: # slight difference
            masked = resize_image(masked, original.size[0], original.size[1]) # resize masked to match original

    print(f"Getting mask for original image with size {original.size} and masked image with size {masked.size}.")
    mask = get_mask(original, masked)
    
    payload = {
        "prompt": text_prompt,
        "image": pil2base64(original),
        "mask_image": pil2base64(mask),
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

def outpaint(image_key, text_prompt, direction):
    if direction not in ["left", "right", "top", "bottom"]:
        raise ValueError("Invalid direction set for outpainting.")

    image = get_image_s3(S3_BUCKET, image_key)
    mask = Image.new('RGB', image.size, color = (255,255,255))
    mime_type = "application/octet-stream"
    image_str = f"data:{mime_type};base64,{pil2base64(image)}" 
    mask_str = f"data:{mime_type};base64,{pil2base64(image)}" 
    url = "https://replicate.com/api/models/devxpy/glid-3-xl-stable/versions/7d6a340e1815acf2b3b2ee0fcaf830fbbcd8697e9712ca63d81930c60484d2d7/predictions"
    payload = {
        "inputs": {
            "prompt": text_prompt,
            "num_inference_steps": 50,
            "edit_image":image_str,
            "mask":mask_str,
            "num_outputs": 1,
            "width": 512, # filler as param doesnt work for output size 
            "height": 512, # filler as param doesnt work for output size
            "outpaint": direction
        }
    }

    headers = {
        "Authorization": f"Token {REPLICATE_TOKEN}",
        "Content-Type": "application/json"
    }
    job = requests.post(url, headers=headers, data=json.dumps(payload).encode('utf-8'))
    if job.status_code in [200, 201]:
        rep_id = job.json()['uuid']
        output_url = f"{url}/{rep_id}"
        while True: # poll for output
            output = requests.get(output_url, headers=headers)
            output_json = output.json()
            if output_json["prediction"]["status"] == "succeeded":
                output_image_url = output_json["prediction"]["output"][0]
                image = Image.open(requests.get(output_image_url, stream = True).raw)
                break
            else:
                time.sleep(10)
                print("Polling Replicate")

    else:
        raise Exception("Failed to post to Replicate API", output.json())
    
    return image



def save_image_s3(image_list, key_prefix):
    np_image = (np.array(image_list)).astype(np.uint8)
    img = Image.fromarray(np_image)

    response = s3.upload_fileobj(pil2bytes(img), S3_BUCKET, f"{key_prefix}/result.jpg")

    return response

def send_photo_telebot(pil_image, chat_id): 
    params = {'chat_id': chat_id}
    files = {'photo': pil2bytes(pil_image)}
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

        details = payload["editing_image_job"]
        job_type = details["job_type"]
        base_key = details["base_image_s3_key"]

        if job_type == "inpainting":
            masked_key = details["mask_image_s3_key"]
        elif job_type == "outpainting":
            outpaint_direction = details["outpaint_direction"]

        if "caption" in payload["message"].keys():
            text_prompt = payload["message"]["caption"]
        else:
            text_prompt = ""
        chat_id = payload["message"]["chat"]["id"]
        base_image_basename = base_key.split("/")[-1].split(".")[0]
        results_key_prefix = f"output/{base_image_basename}"

        if job_type == "inpainting":
            try:
                image = remove(base_key, masked_key, results_key_prefix, text_prompt)
                print("Generated removal image")
            except ValueError as e: 
                if str(e) == "Input images must have the same dimensions.":
                    tele_message = "Sorry, your job has failed as both images must be of the same dimensions. We encourage you to use Telegram's built-in brush tool to generate masked images. This conversation is over now, please type /inpainting to start a new one. Or type /start for a guided workflow."
                    telebot_text_response = send_message_telebot(tele_message, chat_id)
                    return {
                        'statusCode': 501,
                        'body': json.dumps('Input images do not have same dimensions.')
                    }
            except Exception as e:
                tele_message = "Sorry, your job has failed, please try again or contact woaiai. This conversation is over, please restart"
                telebot_text_response = send_message_telebot(tele_message, chat_id)
                print("Error in removal", e)
                return {
                    'statusCode': 500,
                    'body': json.dumps('Error in processing removal.')
                }

            # save_response = save_image_s3(image, results_key_prefix)
            # print("Done saving s3 result")
            print("Sending inpainting image to Telebot")
            np_image = (np.array(image)).astype(np.uint8)
            img = Image.fromarray(np_image)
            telebot_response = send_photo_telebot(img, payload["message"]["chat"]["id"])
        
        elif job_type == "outpainting":
            try:
                outpainted_image = outpaint(base_key, text_prompt, outpaint_direction)
                print("Sending outpainting image to Telebot")
                telebot_outpaint_response = send_photo_telebot(outpainted_image, payload["message"]["chat"]["id"])
            except Exception as e:
                tele_message = "Sorry, your job has failed, please try again or contact woaiai. This conversation is over, please restart"
                telebot_text_response = send_message_telebot(tele_message, chat_id)
                print("Error in outpainting", e)
                return {
                    'statusCode': 500,
                    'body': json.dumps('Error in processing outpainting.')
                }

            return {
                'statusCode': 200,
                'body': json.dumps('Image generated')
            }

        

