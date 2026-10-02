FROM node:24-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:24-slim
WORKDIR /app
ENV NODE_ENV=production \
    PORT=4000
COPY --from=build /app/dist/web ./dist/web
EXPOSE 4000
CMD ["node", "dist/web/server/server.mjs"]
