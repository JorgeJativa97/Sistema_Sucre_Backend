FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 1. Instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    python3-dev \
    libaio1 \
    libaio-dev \
    libnsl2 \
    wget \
    unzip \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 2. Descargar Oracle Instant Client (ya confirmado que funciona)
RUN mkdir -p /opt/oracle && \
    cd /opt/oracle && \
    wget --quiet --show-progress --progress=bar:force \
         --header="Cookie: oraclelicense=accept-securebackup-cookie" \
         https://download.oracle.com/otn_software/linux/instantclient/2114000/instantclient-basic-linux.x64-21.14.0.0.0dbru.zip && \
    unzip instantclient-basic-linux.x64-21.14.0.0.0dbru.zip && \
    rm -f instantclient-basic-linux.x64-21.14.0.0.0dbru.zip

# 3. Configurar Oracle Instant Client
ENV ORACLE_HOME=/opt/oracle/instantclient_21_14
ENV LD_LIBRARY_PATH=/opt/oracle/instantclient_21_14:$LD_LIBRARY_PATH
ENV PATH=/opt/oracle/instantclient_21_14:$PATH

# 4. Verificar que todo esté correcto ANTES de instalar cx-Oracle
RUN echo "=== Verificando instalación de Oracle ===" && \
    ls -la $ORACLE_HOME && \
    echo "=== Librerías principales ===" && \
    ls -la $ORACLE_HOME/libclntsh* && \
    echo "=== Configurando enlaces simbólicos ===" && \
    cd $ORACLE_HOME && \
    ln -sf libclntsh.so.* libclntsh.so && \
    echo "=== Verificando dependencias ===" && \
    ldd $ORACLE_HOME/libclntsh.so | head -10

# 5. Instalar cx-Oracle SOLO primero (para aislar problemas)
COPY requirements.txt .
RUN echo "=== Instalando cx-Oracle primero ===" && \
    pip install --upgrade pip && \
    pip install --no-cache-dir cx-Oracle==8.3.0

# 6. Instalar el resto de dependencias
RUN echo "=== Instalando otras dependencias ===" && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

# 7. Verificar que cx-Oracle funciona
RUN echo "=== Verificando cx-Oracle ===" && \
    python -c "import cx_Oracle; print(f'cx_Oracle versión: {cx_Oracle.__version__}')"

COPY . . 

RUN useradd -m -u 1000 appuser && \
    chown -R appuser: appuser /app
USER appuser

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "Cabildoapp.wsgi:application"]