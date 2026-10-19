FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY src ./src
RUN npm run build

FROM nginx:1.29-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html style.css favicon.svg manifest.webmanifest icon-192.png icon-512.png /usr/share/nginx/html/
COPY --from=build /app/app.js /usr/share/nginx/html/app.js
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
