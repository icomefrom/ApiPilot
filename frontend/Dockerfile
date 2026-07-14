# Build stage
FROM docker.m.daocloud.io/library/node:20-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm config set registry https://registry.npmmirror.com \
    && npm cache clean --force \
    && npm ci --include=dev --include=optional
COPY . .
RUN npm run build

# Production stage
FROM docker.m.daocloud.io/library/nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
