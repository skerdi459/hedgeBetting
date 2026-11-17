# Hedge Slip — Node + SQLite. Works on any container host (Fly.io, Railway, etc.)
FROM node:20-bookworm-slim

WORKDIR /app

# install deps first for better layer caching
COPY package*.json ./
RUN npm ci --omit=dev

COPY . .

# persist the SQLite file on a mounted volume at /data
ENV HEDGE_HOST=0.0.0.0 \
    HEDGE_PORT=3000 \
    HEDGE_DB=/data/hedge.db
VOLUME ["/data"]
EXPOSE 3000

CMD ["node", "server.js"]
