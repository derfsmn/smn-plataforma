FROM python:3.12-slim-bookworm

# Driver ODBC 18 de Microsoft para conectarse a SQL Server
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg ca-certificates \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft.gpg \
    && echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

# Lectura de PDF escaneados e imágenes en Innovación Vidanat (TD005): OCR local en español e inglés, sin servicios externos
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# La API corre con un usuario sin privilegios (revisión de seguridad 2026-11-22, M6); entrypoint.sh arranca como root
# solo para dejarle la carpeta de archivos y luego cambia a ese usuario.
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --home-dir /app --no-create-home app

WORKDIR /app
# En tu equipo se instalan también las herramientas de prueba (probar.ps1 corre pytest aquí);
# en el servidor docker-compose.servidor.yml pasa REQUISITOS=requirements.txt
ARG REQUISITOS=requirements-dev.txt
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r ${REQUISITOS}
COPY --chown=app:app . .
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh && chown app:app /app

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
