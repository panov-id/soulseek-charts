FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /application

# Dependencies are installed from the manifest alone so the layer is cached
# across source changes. The empty package directory is needed because
# setuptools resolves the src layout while building metadata.
COPY pyproject.toml ./
RUN mkdir -p source && pip install --upgrade pip && pip install ".[development]"

COPY source/ ./source/
RUN pip install --no-deps -e .

RUN useradd --create-home --uid 10001 application_user
USER application_user

CMD ["python", "-m", "soulseek_charts.collector"]
