FROM python:3.12-slim

RUN pip install --no-cache-dir gradio==6.29.1 requests==2.32.5
WORKDIR /app
COPY tools/gpu/image_edit_ui.py /app/image_edit_ui.py

ENV GRADIO_ANALYTICS_ENABLED=False \
    GRADIO_SHARE=True \
    IMAGE_EDIT_MODEL_URL=http://gpu-image-edit:30010
EXPOSE 7860
CMD ["python", "/app/image_edit_ui.py"]
