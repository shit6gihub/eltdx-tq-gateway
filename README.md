# eltdx-TQ Gateway v2.0

通达信 TQ 行情网关，支持 **126 个 eltdx 公开方法**，兼容 SIDA v0.4.38。

## 接口

| 端点 | 说明 |
|------|------|
| `POST /` 或 `POST /jsonrpc` | TQ 兼容接口（SIDA v0.4.38 使用） |
| `POST /rpc` | eltdx 原生 RPC 接口 |
| `GET /health` | 健康检查 |
| `GET /methods` | 列出所有可用方法 |

## TQ 兼容映射

| TQ 方法 | eltdx 方法 |
|---------|-----------|
| `get_market_snapshot` | `quotes.get_snapshots` |
| `get_market_data` | `bars.get` |
| `get_more_info` | `quotes.get_snapshots` + F10 |
| `refresh_kline` | 空响应 |

## 支持的 eltdx 方法（126 个）

- **quotes**: 7 个 - 实时行情、盘口、订阅
- **bars**: 1 个 - K 线数据
- **minutes**: 7 个 - 分时数据
- **trades**: 10 个 - 逐笔成交
- **auctions**: 1 个 - 集合竞价
- **limits**: 2 个 - 涨停板
- **codes**: 20 个 - 股票列表
- **f10**: 31 个 - F10 资料
- **helpers**: 24 个 - 板块、排名等
- **workdays**: 12 个 - 交易日计算
- **corporate**: 3 个 - 公司事件
- **session**: 3 个 - 连接管理
- **resources**: 3 个 - 资源文件

## 配置 SIDA

```yaml
environment:
  - PANWATCH_ENABLE_TQ=1
  - TDX_QUANT_URL=http://172.29.0.1:17709
```

重启 panwatch: `docker compose --profile infra up -d --force-recreate panwatch`

## 依赖

```bash
pip install 'eltdx[http]'
```

## 端口

- 默认: 17709
- 绑定: 0.0.0.0

## GitHub

https://github.com/shit6gihub/eltdx-tq-gateway

## 使用方法

### TQ 兼容模式
```bash
curl -X POST http://127.0.0.1:17709/jsonrpc \
  -H "Content-Type: application/json" \
  -d '{"method":"get_market_snapshot","params":{"stock_code":"002600"},"id":1}'
```

### eltdx 原生模式
```bash
curl -X POST http://127.0.0.1:17709/rpc \
  -H "Content-Type: application/json" \
  -d '{"method":"bars.get","params":{"code":"002600","period":"1d","count":5},"id":1}'
```
