# woaiai_hackathon
dsaid hackathon 2023 

## Description
- This folder holds the python code for the telegram bot to be run on the server side. (TODO: Convert to serverless instead of bare metal ec2?)
- .env file contains important tokens to be stored in secrets manager (TODO)
- bot.py scripts saves file to local working directory, overwriting the latest file each time. 

## How to run locally 
- cd woaiai_hackathon
- pip install -r requirements.txt
- python3 bot.py

## How to deploy to AWS
- For now, we will deploy to an internet VPC on bare metal EC2, that EC2 instance will point to github to pull the code to run on the server