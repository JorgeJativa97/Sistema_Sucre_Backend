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
    libaio1t64 \
    wget \
    unzip \
    curl \
    && rm -rf /var/lib/apt/lists/*

# El resto del Dockerfile se mantiene igual...
RUN mkdir -p /opt/oracle && \
    cd /opt/oracle && \
    wget --header="Cookie: oraclelicense=accept-securebackup-cookie" \
         https://download.oracle.com/otn_software/linux/instantclient/191000/instantclient-basic-linux.x64-19.10.0.0.0dbru.zip && \
    unzip instantclient-basic-linux.x64-19.10.0.0.0dbru.zip && \
    rm -f instantclient-basic-linux.x64-19.10.0.0.0dbru.zip

ENV ORACLE_HOME=/opt/oracle/instantclient_19_10
ENV LD_LIBRARY_PATH=/opt/oracle/instantclient_19_10:$LD_LIBRARY_PATH
ENV PATH=/opt/oracle/instantclient_19_10:$PATH
# Configurar enlaces simbólicos
RUN cd $ORACLE_HOME && \
    # Busca cualquier archivo libclntsh.so.* y crea el enlace
    for file in libclntsh.so.*; do \
        if [ -f "$file" ]; then \
            ln -sf "$file" libclntsh.so; \
            echo "Enlazado $file a libclntsh.so"; \
            break; \
        fi; \
    done && \
    # Verifica que el enlace existe
    if [ ! -L libclntsh.so ]; then \
        echo "ERROR: No se pudo crear el enlace"; \
        exit 1; \
    fi

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