# Inpainting / Removal 
- Processing of images handled by Lambda
- Stable Diffusion inpainting handled by Sagemaker asynchronous inference endpoint (with auto-scaling)

## Deploy Sagemaker endpoint 
Run notebook `Sagemaker SD Inpainting Deployment.ipynb` in Sagemaker Studio. 

## Deploy Lambda

1. Create Docker image locally 

```
docker build -f Dockerfile -t woaiai-removal-lambda:latest .
```

2. Push Docker image to ECR
- Pre-requisites: AWS CLI profile, Serverless
- Create ECR repository
```
aws ecr create-repository --repository-name woaiai-removal-lambda --profile woaiai
```
- Get ECR authentication

```
aws ecr get-login-password --region ap-southeast-1 --profile woaiai | docker login --username AWS --password-stdin 159762733383.dkr.ecr.ap-southeast-1.amazonaws.com
```
- Tag local Docker image
```
docker tag woaiai-removal 159762733383.dkr.ecr.ap-southeast-1.amazonaws.com/woaiai-removal-lambda
```
- Push local Docker image to ECR
```
docker push 159762733383.dkr.ecr.ap-southeast-1.amazonaws.com/woaiai-removal-lambda
```

3. Deploy to AWS with Serverless

```
serverless deploy --aws-profile woaiai --force
```

