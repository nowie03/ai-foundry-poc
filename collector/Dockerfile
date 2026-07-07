# Use the official OTel collector contrib base image
FROM otel/opentelemetry-collector-contrib:latest

# Copy configuration files into the image
COPY collector-config.dev.yaml /etc/otelcol/collector-config.dev.yaml
COPY collector-config.prod.yaml /etc/otelcol/collector-config.prod.yaml
COPY collector-config.debug.yaml /etc/otelcol/collector-config.debug.yaml

# Set default configuration to dev config
# Can be overridden by specifying another config via command line arguments
CMD ["--config=/etc/otelcol/collector-config.dev.yaml"]
