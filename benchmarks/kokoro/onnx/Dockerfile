FROM --platform=linux/arm64 python:3.12-slim-bookworm
RUN pip install --no-cache-dir kokoro-onnx==0.6.1 soundfile numpy
ADD https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx /models/kokoro-v1.0.onnx
ADD https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin /models/voices-v1.0.bin
