FROM python:3.12-alpine AS seo
WORKDIR /src
COPY requirements.txt seoslug-config.toml ./
COPY scripts/ scripts/
COPY content/ content/
RUN pip install --no-cache-dir -r requirements.txt && \
    python scripts/generate_seo.py

FROM hugomods/hugo:exts AS builder
WORKDIR /src
COPY --from=seo /src/data/ ./data/
COPY . .
RUN hugo --minify

FROM nginx:alpine
COPY --from=builder /src/public /usr/share/nginx/html
