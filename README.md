# eltdx-TQ Gateway Docker

基于 eltdx 的通达信行情网关，支持 SIDA v0.4.38 TQ 接口。

## 特性

- 支持 126 个 eltdx 公开方法
- TQ 兼容接口（适配 SIDA）
- Docker 镜像自动构建

## 使用方法

### 从 Docker Hub 拉取

```bash
docker pull ghcr.io/shit6gihub/eltdx-tq-gateway:latest
```

### 运行容器

```bash
docker run -d \
  --name eltdx-tq-gateway \
  -p 17709:17709 \
  --restart unless-stopped \
  ghcr.io/shit6gihub/eltdx-tq-gateway:latest
```

### 与健康检查

```bash
curl http://localhost:17709/health
```

## SIDA 配置

在 `docker-compose.yml` 中添加：

```yaml
environment:
  - PANWATCH_ENABLE_TQ=1
  - TDX_QUANT_URL=http://host.docker.internal:17709
```

## API 端点

| 端点 | 说明 |
|------|------|
| `POST /` | TQ 兼容接口 |
| `POST /jsonrpc` | TQ JSON-RPC 接口 |
| `POST /rpc` | eltdx 原生 RPC 接口 |
| `GET /health` | 健康检查 |
| `GET /methods` | 方法列表 |

## GitHub Actions

当推送代码到 main 分支时，自动构建 Docker 镜像并推送到 GitHub Container Registry。

也可以手动触发构建：
https://github.com/shit6gihub/eltdx-tq-gateway/actions
