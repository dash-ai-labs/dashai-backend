FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN python -m pip install --upgrade pip \
    && mkdir -p /workspace/dash_ai

WORKDIR /workspace/dash_ai

COPY ./model_cache /workspace/dash_ai/model_cache
COPY requirements.txt /workspace/dash_ai/requirements.txt

RUN pip install -r ./requirements.txt
    
COPY . /workspace/dash_ai/