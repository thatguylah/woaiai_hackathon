resource "aws_ecs_cluster" "image-processing-cluster" {
  name = "image-processing-cluster"
}

resource "aws_ecr_repository" "image-processing-repo" {
  name = "image-processing-repo"
}

resource "aws_ecr_lifecycle_policy" "lifecycle_policy" {
  repository = aws_ecr_repository.image-processing-repo.name

  policy = jsonencode({
    rules = [
      {
        "rulePriority" : 1,
        "description" : "Expire images older than 7 days",
        "selection" : {
          "tagStatus" : "any",
          "countType" : "sinceImagePushed",
          "countUnit" : "days",
          "countNumber" : 7
        },
        "action" : {
          "type" : "expire"
        }
      }
    ]
  })
}

# resource "aws_ecr_repository_policy" "repository_policy" {
#   repository = aws_ecr_repository.image-processing-repo.name

#   policy = jsonencode({
#     "Version": "2008-10-17",
#     "Statement": [
#       {
#         "Sid": "AllowPull",
#         "Effect": "Allow",
#         "Principal": "*",
#         "Action": [
#           "ecr:GetDownloadUrlForLayer",
#           "ecr:BatchGetImage",
#           "ecr:BatchCheckLayerAvailability"
#         ]
#       }
#     ]
#   })
# }

# # Provision the Docker image to ECR
# resource "null_resource" "push_to_ecr" {
#   triggers = {
#     repository_id = aws_ecr_repository.image-processing-repo.id
#     image_tag     = "webserver"
#   }

#     provisioner "local-exec" {
#         command = <<EOF
#     $(aws ecr get-login-password --no-include-email --region ap-southeast-1)
#     docker build -t ${aws_ecr_repository.image-processing-repo.repository_url}:webserver .
#     docker push ${aws_ecr_repository.image-processing-repo.repository_url}:webserver
#     EOF
#     }
# }

resource "aws_iam_role" "image_processing_task_role" {
  name = "image_processing_task_role"

  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF
}

resource "aws_iam_role_policy_attachment" "attachment_cloudwatch_logs" {
  role       = aws_iam_role.image_processing_task_role.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchLogsFullAccess"
}

resource "aws_iam_role_policy_attachment" "attachment_s3" {
  role       = aws_iam_role.image_processing_task_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3FullAccess"
}
resource "aws_iam_role_policy_attachment" "attachment_ecr" {
  role       = aws_iam_role.image_processing_task_role.name
  policy_arn = "arn:aws:iam::aws:policy/EC2InstanceProfileForImageBuilderECRContainerBuilds"
}

# Create CW Logs group
resource "aws_cloudwatch_log_group" "ecs_fargate_log_group" {
  name = "/ecs/fargate-task-definition"
}

# Define the task definition
resource "aws_ecs_task_definition" "image_processing_task_definition" {
  family                   = "image_processing_task_definition" # Update with your desired task definition name
  execution_role_arn       = aws_iam_role.image_processing_task_role.arn
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 256
  memory                   = 512
  container_definitions = jsonencode([
    {
      "name" : "image-processing-container",
      "image" : "${aws_ecr_repository.image-processing-repo.repository_url}",
      "logConfiguration" : {
        "logDriver" : "awslogs",
        "options" : {
          "awslogs-group" : "/ecs/fargate-task-definition",
          "awslogs-region" : "ap-southeast-1",
          "awslogs-stream-prefix" : "ecs"
        }
      },
      "portMappings" : [
        {
          "containerPort" : 8000,
          "hostPort" : 8000,
          "protocol" : "tcp"
        }
      ]
    }
  ])
}

resource "aws_ecs_service" "image-processing-service" {
  name            = "image-processing-service"
  cluster         = aws_ecs_cluster.image-processing-cluster.id
  task_definition = aws_ecs_task_definition.image_processing_task_definition.arn
  desired_count   = 1

  network_configuration {
    subnets          = ["subnet-0ae6ac77a21356265", "subnet-0ddd5c5d96551768a", "subnet-0e4e944a838b1e8d4"]
    security_groups  = ["sg-0aa3b110f83d01274"]
    assign_public_ip = false
  }
}
