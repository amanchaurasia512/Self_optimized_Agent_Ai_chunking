# PDF chunking agent, local app v1 (spec/agent_v1.md, App v1). Keys are never in the image: the provider list and key
# files are mounted at run time from ~/.config/pdf-agent/ (see README). Build from the repo root:
#   docker build -t pdf-agent .
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/models/huggingface AGENT_MACHINE=docker
# git only so run records can state that there is no commit (the image has no .git): code.commit is null.
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 git \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 1000 app && mkdir -p /opt/models && chown app /opt/models
WORKDIR /app

# The Docling environment's exact versions (docs/constraints-app.txt: the docling and app extras and what they
# resolved to), with CPU torch. `pip install ".[docling,app]"` cannot resolve: the base dependencies pin the study's
# huggingface_hub 2.3.0 and Docling needs < 2 (docs/environment.md), so the project goes in with --no-deps, editable,
# which keeps PROJECT_ROOT at /app (data/agent_cache, runs/, pdfs/*.csv).
COPY docs/constraints-app.txt docs/constraints-app.txt
RUN pip install torch==2.15.0 torchvision==0.29.2 --index-url https://download.pytorch.org/whl/cpu \
    && grep -v "^torch==\|^torchvision==" docs/constraints-app.txt > /tmp/requirements.txt \
    && pip install -r /tmp/requirements.txt && rm /tmp/requirements.txt
COPY pyproject.toml README.md ./
COPY src src
COPY scripts scripts
RUN pip install --no-deps -e .
COPY app app
COPY .streamlit .streamlit
COPY spec spec
COPY pdfs/catalog.csv pdfs/split.csv pdfs/

USER app
# Models at build time: bge-m3 and its tokenizer at the study's pinned revision, and Docling's layout, table and OCR
# models; the container then runs offline.
RUN python -c "from src.agent.index import encoder; from src.chunk.base import tokenizer; encoder(); tokenizer()" \
    && python -c "from docling.datamodel.base_models import InputFormat; from src.agent.pipeline import docling_converter; \
docling_converter()[0].initialize_pipeline(InputFormat.PDF)"
ENV HF_HUB_OFFLINE=1
USER root
RUN mkdir -p /app/data/agent_cache /app/runs /home/app/.config/pdf-agent && chown -R app /app/data /app/runs /home/app/.config
USER app

EXPOSE 8501
CMD ["streamlit", "run", "app/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
