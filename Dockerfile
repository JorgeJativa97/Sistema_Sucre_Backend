FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# CORREGIDO: Nombres de paquetes para Debian 12 (trixie)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    python3-dev \
    # Paquetes CORREGIDOS para Debian 12:
    libaio1t64 \          # En lugar de libaio1
    libaio-dev \          # Este se mantiene igual
    libnsl2 \             # En lugar de libnsl (si es necesario)
    wget \
    unzip \
    curl \
    && rm -rf /var/lib/apt/lists/*

# El resto del Dockerfile se mantiene igual...
RUN mkdir -p /opt/oracle && \
    cd /opt/oracle && \
    wget --quiet --show-progress --progress=bar:force \
         --header="Cookie: oraclelicense=accept-securebackup-cookie" \
         https://download.oracle.com/otn_software/linux/instantclient/2114000/instantclient-basic-linux.x64-21.14.0.0.0dbru.zip && \
    unzip instantclient-basic-linux.x64-21.14.0.0.0dbru.zip && \
    rm -f instantclient-basic-linux.x64-21.14.0.0.0dbru.zip

ENV ORACLE_HOME=/opt/oracle/instantclient_21_14
ENV LD_LIBRARY_PATH=/opt/oracle/instantclient_21_14:$LD_LIBRARY_PATH
ENV PATH=/opt/oracle/instantclient_21_14:$PATH

# Configurar enlaces simbólicos
RUN cd $ORACLE_HOME && \
    ln -sf libclntsh.so.* libclntsh.so

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

COPY . . 

RUN useradd -m -u 1000 appuser && \
    chown -R appuser: appuser /app
USER appuser

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "Cabildoapp.wsgi:application"]