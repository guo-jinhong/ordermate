# ===== 构建阶段：安装依赖 + 校验 + 构建 =====
FROM node:24-alpine AS builder

WORKDIR /app

# 只复制依赖描述文件，利用 Docker 层缓存
COPY package.json package-lock.json ./

# ci 比 install 更严格、可复现，用于生产构建
RUN npm ci

# 复制源码并执行完整校验（类型检查 + 构建 + 单测 + 构建契约测试）
COPY . .
RUN npm run validate

# ===== 运行阶段：Nginx 仅托管 dist =====
FROM nginx:1.27-alpine AS runtime

# 移除默认配置，使用项目自定义配置
RUN rm /etc/nginx/conf.d/default.conf

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

# Nginx 健康检查：容器内访问首页，确认 dist 已正确部署
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -q --spider http://localhost/ || exit 1

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
