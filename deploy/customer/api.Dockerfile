ARG BASE_IMAGE=changwei-api:0.7.2.beta2
FROM ${BASE_IMAGE} AS compiler
USER 0:0
RUN sed -i 's|http://mirrors.tuna.tsinghua.edu.cn/debian-security|https://deb.debian.org/debian-security|g; s|http://mirrors.tuna.tsinghua.edu.cn/debian|https://deb.debian.org/debian|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=2 -o Acquire::https::Timeout=40 update \
    && apt-get -o Acquire::Retries=2 -o Acquire::https::Timeout=40 install -y --no-install-recommends gcc libc6-dev binutils \
    && python -m pip install --no-cache-dir --index-url https://pypi.org/simple 'Cython==3.3.0'
COPY backend/package /release/package
COPY backend/server /release/server
COPY LICENSE /release/LICENSE
COPY deploy/customer/compile_core.py /build-tools/compile_core.py
RUN python /build-tools/compile_core.py

FROM ${BASE_IMAGE} AS assembled
USER 0:0
# 仅清理本镜像构建阶段的旧应用目录；发布阶段从干净根文件系统复制。
RUN rm -rf /app/package /app/server /app/uv.lock /app/pyproject.toml /app/.python-version \
    && mkdir -p /app/runtime /app/user-data /app/skill-sources /app/skill-projections
COPY --from=compiler /release /app
RUN chown -R 1000:1000 /app/runtime /app/user-data /app/skill-sources /app/skill-projections

# 不继承编译阶段或旧应用镜像层，防止通过历史层恢复被移除的源码。
FROM scratch
COPY --from=assembled / /
ENV PATH=/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin \
    HOME=/home/yuxi TZ=Asia/Shanghai PYTHONPATH=/app/package \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    NLTK_DATA=/home/yuxi/nltk_data RAPIDOCR_MODEL_DIR=/home/yuxi/.cache/rapidocr/models
WORKDIR /app
USER 1000:1000
ENTRYPOINT ["/usr/local/bin/yuxi-entrypoint"]
CMD ["python", "-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "5050"]
LABEL org.opencontainers.image.title="Jiangqing" org.opencontainers.image.version="0.2.0" \
      org.opencontainers.image.description="Engineering workflow trial; six business modules compiled; upstream MIT framework retained."
