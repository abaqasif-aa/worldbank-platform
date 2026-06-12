FROM python:3.11-slim

WORKDIR /dbt

RUN pip install --no-cache-dir \
    dbt-postgres==1.7.0 \
    protobuf==4.25.3

COPY . .

ENTRYPOINT ["dbt"]
CMD ["--help"]
