FROM node:22-alpine

ENV NODE_ENV=production \
    PORT=3000 \
    MUSIC_DIR=/music \
    DATA_DIR=/data

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY server.js ./
COPY public ./public

RUN mkdir -p /music /data && chown node:node /music /data
USER node

EXPOSE 3000
HEALTHCHECK --interval=60s --timeout=5s --start-period=20s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3000/healthz >/dev/null || exit 1

CMD ["node", "server.js"]
