FROM python:3.13-slim
RUN useradd -m app
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir gunicorn
COPY qleric/ qleric/
COPY api.py .
RUN chown -R app:app /app
USER app
ENV PORT=5000
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','5000')+'/health',timeout=4)"
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "api:app"]
