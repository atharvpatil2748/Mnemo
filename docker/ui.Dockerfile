FROM node:22-alpine AS dependencies

RUN corepack enable
WORKDIR /app

COPY mnemo-ui/package.json mnemo-ui/pnpm-lock.yaml mnemo-ui/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM dependencies AS development

COPY mnemo-ui/ ./

CMD ["pnpm", "dev"]

FROM dependencies AS build

COPY mnemo-ui/ ./
RUN pnpm build

FROM nginx:1.29-alpine

COPY --from=build /app/dist /usr/share/nginx/html

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD wget --quiet --tries=1 --spider http://127.0.0.1/ || exit 1
