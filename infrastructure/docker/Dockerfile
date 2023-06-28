# Define custom function directory
ARG FUNCTION_DIR="/function"

FROM python:3.8 as build-image

# Include global arg in this stage of the build
ARG FUNCTION_DIR

# Copy function code
RUN mkdir -p ${FUNCTION_DIR}
COPY . ${FUNCTION_DIR}

# Use a slim version of the base Python image to reduce the final image size
FROM python:3.8-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends libgl1-mesa-glx libglib2.0-0 build-essential

# Include global arg in this stage of the build
ARG FUNCTION_DIR
# Set working directory to function root directory
WORKDIR ${FUNCTION_DIR}

# Copy in the built dependencies
COPY --from=build-image ${FUNCTION_DIR} ${FUNCTION_DIR}

# Copy the requirements file to the container
COPY requirements.txt ${FUNCTION_DIR}

# Install the function's dependencies
RUN pip install \
    --no-cache-dir \
    --target ${FUNCTION_DIR} \
    awslambdaric

RUN pip install \
    --no-cache-dir \
    --target ${FUNCTION_DIR} \
    -r requirements.txt

# Set runtime interface client as default command for the container runtime
ENTRYPOINT [ "/usr/local/bin/python", "-m", "awslambdaric" ]
# Pass the name of the function handler as an argument to the runtime
CMD [ "lambda_function.handler" ]
