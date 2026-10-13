FROM node:22-alpine AS dependencias
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS construccion
WORKDIR /app
COPY --from=dependencias /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=construccion /app/.next/standalone ./
COPY --from=construccion /app/.next/static ./.next/static
COPY --from=construccion /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
