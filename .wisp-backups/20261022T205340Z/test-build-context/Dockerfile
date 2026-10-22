FROM wisp-chom-reviewed:d8a4baf-4602fa2b

RUN apk add --no-cache git nodejs
COPY requirements-dev.txt /tmp/requirements-dev.txt
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements-dev.txt

WORKDIR /src
ENTRYPOINT []
CMD ["python", "-m", "pytest", "-p", "no:cacheprovider", "-q"]
