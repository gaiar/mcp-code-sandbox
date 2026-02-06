FROM python:3.12-slim

# Install scientific packages in a single layer
RUN pip install --no-cache-dir \
    pandas \
    numpy \
    matplotlib \
    seaborn \
    openpyxl \
    reportlab \
    pyarrow \
    scipy

# Create working directory
RUN mkdir -p /mnt/data

# Create non-root user
RUN useradd --create-home --shell /bin/bash sandbox
RUN chown sandbox:sandbox /mnt/data

USER sandbox
WORKDIR /mnt/data
