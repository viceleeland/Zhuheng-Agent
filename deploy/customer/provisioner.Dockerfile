FROM yuxi-sandbox-provisioner:0.7.2.beta2
RUN python -m pip install --no-cache-dir --index-url https://pypi.org/simple 'docker==7.2.0'
COPY docker/sandbox_provisioner/app.py /app/app.py
COPY docker/sandbox_provisioner/sandbox.env /app/sandbox.env
COPY deploy/customer/patch_provisioner.py /tmp/patch_provisioner.py
RUN python /tmp/patch_provisioner.py /app/app.py && rm /tmp/patch_provisioner.py
LABEL org.opencontainers.image.title="Jiangqing sandbox provisioner" org.opencontainers.image.version="0.2.0"
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8002"]
