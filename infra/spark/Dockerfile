
FROM apache/spark:3.5.6

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential librdkafka-dev && \
    rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir pyarrow pandas fastavro
RUN mkdir -p /home/spark/.ivy2/cache /home/spark/.ivy2/jars && chown -R spark:spark /home/spark/.ivy2
USER spark
