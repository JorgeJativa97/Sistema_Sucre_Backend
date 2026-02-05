FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencias del sistema (Debian trixie)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ python3-dev \
    libaio1t64 \
    wget unzip curl \
    && rm -rf /var/lib/apt/lists/*

# ?? Oracle espera libaio.so.1 (no t64)
RUN ln -s /usr/lib/x86_64-linux-gnu/libaio.so.1t64 \
          /usr/lib/x86_64-linux-gnu/libaio.so.1

# Oracle Instant Client
RUN mkdir -p /opt/oracle && cd /opt/oracle && \
    wget --header="Cookie: oraclelicense=accept-securebackup-cookie" \
    https://download.oracle.com/otn_software/linux/instantclient/191000/instantclient-basic-linux.x64-19.10.0.0.0dbru.zip && \
    unzip instantclient-basic-linux.x64-19.10.0.0.0dbru.zip && \
    rm -f instantclient-basic-linux.x64-19.10.0.0.0dbru.zip

ENV ORACLE_HOME=/opt/oracle/instantclient_19_10
ENV LD_LIBRARY_PATH=/opt/oracle/instantclient_19_10
ENV PATH=/opt/oracle/instantclient_19_10:$PATH

RUN cd /opt/oracle/instantclient_19_10 && \
    ln -sf libclntsh.so.19.1 libclntsh.so

# Python deps
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

COPY . .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "Cabildoapp.wsgi:application"]
