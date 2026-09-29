FROM public.ecr.aws/docker/library/python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl libglib2.0-0 libgl1 libgomp1 libfontconfig1 libfreetype6 libxrender1 libxext6 openjdk-17-jre-headless && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/pdf2html
RUN curl -fL https://github.com/pdf2htmlEX/pdf2htmlEX/releases/download/v0.18.8.rc1/pdf2htmlEX-0.18.8.rc1-master-20200630-Ubuntu-focal-x86_64.AppImage -o converter.AppImage && chmod +x converter.AppImage && ./converter.AppImage --appimage-extract >/dev/null && rm converter.AppImage
RUN chmod -R a+rX /opt/pdf2html && printf '#!/bin/sh\nexec /opt/pdf2html/squashfs-root/AppRun "$@"\n' > /usr/local/bin/pdf2htmlEX && chmod +x /usr/local/bin/pdf2htmlEX && su -s /bin/sh nobody -c 'pdf2htmlEX --version'
WORKDIR /app
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -c "from pathlib import Path; from docling.utils.model_downloader import download_models; download_models(Path('/opt/models'), with_code_formula=False, with_picture_classifier=False, with_rapidocr=False)" && chmod -R a+rX /opt/models
ENV HOME=/tmp HF_HOME=/tmp/huggingface XDG_CACHE_HOME=/tmp/cache OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 TOKENIZERS_PARALLELISM=false
COPY backend/ /app/
RUN python -c "import opendataloader_pdf; import docling; import pypdf"
ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["worker.handler"]
