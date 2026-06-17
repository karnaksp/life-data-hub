FROM apache/hive:3.1.3

USER root

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /tmp/deps /opt/hadoop/share/hadoop/common/lib && \
    curl -o /tmp/deps/hadoop-aws-3.1.0.jar \
    https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.1.0/hadoop-aws-3.1.0.jar && \
    curl -o /tmp/deps/aws-java-sdk-bundle-1.11.271.jar \
    https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.11.271/aws-java-sdk-bundle-1.11.271.jar && \
    curl -o /tmp/deps/iceberg-hive-runtime-1.9.2.jar \
    https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-hive-runtime/1.9.2/iceberg-hive-runtime-1.9.2.jar && \
    cp /tmp/deps/*.jar /opt/hive/lib/ && \
    cp /tmp/deps/*.jar /opt/hadoop/share/hadoop/common/lib/ && \
    rm -rf /tmp/deps

COPY config/hive-site.xml /opt/hive/conf/hive-site.xml
COPY config/core-site.xml /opt/hive/conf/core-site.xml
COPY entrypoint.sh /entrypoint.sh

RUN chmod 644 /opt/hive/lib/hadoop-aws-3.1.0.jar /opt/hive/lib/aws-java-sdk-bundle-1.11.271.jar /opt/hive/lib/iceberg-hive-runtime-1.9.2.jar /opt/hadoop/share/hadoop/common/lib/hadoop-aws-3.1.0.jar /opt/hadoop/share/hadoop/common/lib/aws-java-sdk-bundle-1.11.271.jar /opt/hadoop/share/hadoop/common/lib/iceberg-hive-runtime-1.9.2.jar /opt/hive/conf/hive-site.xml /opt/hive/conf/core-site.xml && \
    chmod +x /entrypoint.sh

USER hive

ENTRYPOINT ["/entrypoint.sh"]
