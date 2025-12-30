FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libaio1t64 \
    wget \
    unzip \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/oracle && \
    cd /opt/oracle && \
    wget https://download.oracle.com/otn_software/linux/instantclient/2110000/instantclient-basic-linux.x64-21.10.0.0.0dbru.zip && \
    unzip instantclient-basic-linux.x64-21.10.0.0.0dbru.zip && \
    rm -f instantclient-basic-linux.x64-21.10.0.0.0dbru.zip

ENV LD_LIBRARY_PATH=/opt/oracle/instantclient_21_10:$LD_LIBRARY_PATH
ENV PATH=/opt/oracle/instantclient_21_10:$PATH

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --only-binary cx-Oracle -r requirements.txt && \
    pip install --no-cache-dir gunicorn

COPY . . 

RUN useradd -m -u 1000 appuser && \
    chown -R appuser: appuser /app
USER appuser

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "Cabildoapp.wsgi:application"]