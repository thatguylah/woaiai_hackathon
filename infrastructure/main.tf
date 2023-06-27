terraform {
  required_version = ">= 1.0.0"
  backend "s3" {
    bucket         = "central-components"
    key            = "terraform.tfstate"
    region         = "ap-southeast-1"
    encrypt        = true
  }
}

provider "aws" {
  region = "ap-southeast-1"
}

resource "aws_sqs_queue" "msg_incoming_queue" {
  name = "msg_incoming_queue"
}

resource "aws_s3_bucket" "telegram_bot_images" {
  bucket = "dsaid-hackathon-tele-bot-images"
}

resource "aws_s3_bucket_versioning" "telegram_bot_images_versioning" {
  bucket = aws_s3_bucket.telegram_bot_images.id
  versioning_configuration {
    status = "Enabled"
  }
}

module "image-processing-service" {
    source = "./modules/"
}


