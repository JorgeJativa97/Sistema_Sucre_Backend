FROM python:3.11-slim
RUN apt-get update && apt-get install -y wget unzip
RUN mkdir -p /opt/oracle && cd /opt/oracle && \
    wget --header="Cookie: oraclelicense=accept-securebackup-cookie" \
         https://download.oracle.com/otn_software/linux/instantclient/2114000/instantclient-basic-linux.x64-21.14.0.0.0dbru.zip && \
    unzip instantclient-basic-linux.x64-21.14.0.0.0dbru.zip && \
    ls -la instantclient_21_14/