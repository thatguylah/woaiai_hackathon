FROM public.ecr.aws/lambda/python:3.8


COPY requirements.txt ./
RUN pip3 install -r requirements.txt --target "$LAMBDA_RUNTIME_DIR"
COPY infer.py ${LAMBDA_TASK_ROOT}

CMD ["infer.handler"]