FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home portal
COPY --chown=portal:portal app ./app
RUN mkdir /data && chown portal:portal /data
USER portal
ENV PORTAL_DATA=/data
EXPOSE 8000
CMD ["python","-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
