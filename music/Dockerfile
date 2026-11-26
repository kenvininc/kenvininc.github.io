FROM node:22-alpine

ENV NODE_ENV=production \
    PORT=3000 \
    MUSIC_DIR=/music \
    DATA_DIR=/data

WORKDIR /app
COPY package.json package-lock.json ./
RUN chmod a+r package.json package-lock.json \
 && npm ci --omit=dev && npm cache clean --force
COPY server.js ./
COPY public ./public
# Files copied from a NAS share can keep restrictive modes (e.g. 0600 owned by root).
# The container runs as an arbitrary uid (compose `user:`), so make the app world-readable.
RUN chmod -R a+rX /app \
 && mkdir -p /music /data && chown node:node /music /data
USER node

EXPOSE 3000
HEALTHCHECK --interval=60s --timeout=5s --start-period=20s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3000/healthz >/dev/null || exit 1

CMD ["node", "server.js"]
