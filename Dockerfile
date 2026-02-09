# Basis-Image: Python 3.11 Slim (klein & sicher)
FROM python:3.11-slim

# Arbeitsverzeichnis im Container setzen
WORKDIR /app

# Abhängigkeiten kopieren und installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Den Rest des Codes (main.py, templates/) kopieren
COPY . .

# Port 8000 exponieren (Dokumentation)
EXPOSE 8000

# Startbefehl: Uvicorn Server starten
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]