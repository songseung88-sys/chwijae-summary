FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Seoul
WORKDIR /app
COPY archive/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY archive/main.py ./main.py
COPY archive/bootstrap.py ./bootstrap.py
COPY collector/main.py ./collector_parser.py
ENTRYPOINT ["python","bootstrap.py"]
CMD ["--mode","full","--days","7"]
