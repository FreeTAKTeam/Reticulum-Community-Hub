FROM rust:1.99.1-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
    libdbus-1-dev libssl-dev pkg-config dpkg-dev \
    && rm -rf /var/lib/apt/lists/*
ENV RUSTUP_TOOLCHAIN=1.99.1
