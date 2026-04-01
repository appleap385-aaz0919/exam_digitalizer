FROM node:20-alpine AS base

WORKDIR /app

# 의존성 설치
FROM base AS deps
COPY package.json package-lock.json* ./
RUN npm ci

# 빌드
FROM base AS builder
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# 실행
FROM base AS runner
ENV NODE_ENV=production

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
