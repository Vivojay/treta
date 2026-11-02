FROM node:22.18.0-alpine

WORKDIR /app
RUN corepack enable && corepack prepare pnpm@10.14.0 --activate && \
    addgroup -S treta && adduser -S -G treta -u 10001 treta
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json ./apps/web/package.json
RUN pnpm install --frozen-lockfile
COPY apps/web ./apps/web
RUN chown -R treta:treta /app
USER 10001
EXPOSE 5173
CMD ["pnpm", "--dir", "apps/web", "dev", "--host", "0.0.0.0"]
