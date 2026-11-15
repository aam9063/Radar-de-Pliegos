# syntax=docker/dockerfile:1

FROM node:24-alpine AS build

RUN corepack enable

WORKDIR /app

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .

# Vite inlines the API base URL at build time, so it must be present before the
# build runs. Hosts that configure build variables (NaN Cloud, Render) pass it
# as a Docker build argument.
ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}

RUN pnpm build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
