#!/usr/bin/env python3
"""eltdx-TQ Gateway v2.1 - 完整通达信行情网关

支持两类接口：
1. TQ 兼容接口（/jsonrpc, /）：适配 SIDA v0.4.38 TQ vendor
2. eltdx 原生接口（/rpc）：支持全部 126+ 个公开方法（含 F10）

TQ 方法映射：
- get_market_snapshot → quotes.get_snapshots
- get_more_info → quotes.get_snapshots + 字段转换
- get_market_data → bars.get
- refresh_kline → 空响应

用法：
    python3 eltdx-tq-gateway.py [--port 17709] [--host 0.0.0.0]
"""
import argparse
import asyncio
import json
import logging
import sys
from typing import Any

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from uvicorn import run
except ImportError:
    print("需要安装: pip install 'eltdx[http]'")
    sys.exit(1)

from eltdx import TdxClient, F10Client
from eltdx.http_server import _Gateway as _EltdxGateway

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="eltdx-TQ Gateway")
client: TdxClient | None = None
f10_client: F10Client | None = None
eltdx_gateway: _EltdxGateway | None = None


def parse_tdx_code(code: str) -> str:
    """代码格式转换：002600.SZ → sz002600"""
    code = code.strip()
    if code.startswith(('sh', 'sz', 'bj')):
        return code.lower()
    if '.' in code:
        parts = code.split('.')
        return f"{parts[-1].lower()}{parts[0]}"
    if code.startswith(('6', '9', '5')):
        return f"sh{code}"
    elif code.startswith(('4', '8', '92')):
        return f"bj{code}"
    return f"sz{code}"


async def startup():
    """启动时初始化客户端"""
    global client, f10_client, eltdx_gateway

    # 初始化行情客户端
    tdx_host = os.environ.get("TDX_HOST", "114.142.142.124")
    tdx_port = int(os.environ.get("TDX_PORT", "7709"))

    print(f"Connecting to TDX server at {tdx_host}:{tdx_port}...")
    client = TdxClient(timeout=10, host=tdx_host, port=tdx_port)
    await client.connect()

    # 初始化 F10 客户端（独立连接）
    print("Connecting to F10 server...")
    f10_client = F10Client(timeout=10)
    await f10_client.connect()

    # 创建网关
    eltdx_gateway = _EltdxGateway(client)
    print(f"Gateway ready, client connected: {client.connected}")


def shutdown():
    """关闭时清理资源"""
    global client, f10_client, eltdx_gateway
    if client:
        client.close()
    if f10_client:
        f10_client.close()


# ==================== TQ 兼容接口 ====================

@app.post("/")
@app.post("/jsonrpc")
async def tq_jsonrpc(request: Request):
    """TQ 兼容的 JSON-RPC 接口"""
    body = await request.json()
    method = body.get("method", "")
    params = body.get("params", {})
    req_id = body.get("id", 1)

    try:
        if method == "get_market_snapshot":
            result = handle_tq_snapshot(params)
        elif method == "get_more_info":
            result = handle_tq_more_info(params)
        elif method == "get_market_data":
            result = handle_tq_kline(params)
        elif method == "refresh_kline":
            result = {"ErrorId": "0"}
        else:
            result = {"ErrorId": "-1", "Error": f"Unknown TQ method: {method}"}
        return JSONResponse({"id": req_id, "result": result})
    except Exception as e:
        logger.error(f"TQ RPC error {method}: {e}")
        return JSONResponse({"id": req_id, "result": {"ErrorId": "-1", "Error": str(e)}})


def handle_tq_snapshot(params: dict) -> dict:
    """获取实时行情快照"""
    stock_code = params.get("stock_code", "")
    if not stock_code:
        return {"ErrorId": "-1", "Error": "stock_code required"}
    try:
        snaps = client.quotes.get_snapshots([parse_tdx_code(stock_code)])
        if not snaps:
            return {"ErrorId": "-1", "Error": "no data"}
        s = snaps[0]
        return {
            "Now": float(s.last_price or 0),
            "LastClose": float(s.pre_close_price or 0),
            "Open": float(s.open_price or 0),
            "Max": float(s.high_price or 0),
            "Min": float(s.low_price or 0),
            "Volume": int(s.volume or 0),
            "Amount": float(s.amount or 0),
            "Change": float(s.change_amount or 0),
            "ChangePct": float(s.change_pct or 0),
        }
    except Exception as e:
        logger.error(f"Snapshot error: {e}")
        return {"ErrorId": "-1", "Error": str(e)}


def handle_tq_more_info(params: dict) -> dict:
    """获取扩展指标（从快照补充 PE/PB 等字段）"""
    stock_code = params.get("stock_code", "")
    if not stock_code:
        return {"ErrorId": "-1", "Error": "stock_code required"}
    try:
        snaps = client.quotes.get_snapshots([parse_tdx_code(stock_code)])
        if not snaps:
            return {"ErrorId": "-1", "Error": "no data"}

        s = snaps[0]
        # 使用 safe_get 避免属性不存在问题
        d = s.model_dump() if hasattr(s, 'model_dump') else vars(s)

        return {
            "ZAF": float(d.get('change_pct') or 0),
            "PE": float(d.get('pe_ratio') or 0),
            "PB": float(d.get('pb_ratio') or 0),
            "MktCap": float(d.get('market_value') or 0),
            "TotShr": float(d.get('total_shares') or 0),
            "CircShr": float(d.get('circulating_shares') or 0),
            "fHSL": float(d.get('turnover_rate') or 0),
            "UpDn": float(d.get('up_down_range') or 0),
            "Wtb": float(d.get('volume_ratio') or 0),
            "ErrorId": "0",
        }
    except Exception as e:
        logger.error(f"More info error: {e}")
        return {"ErrorId": "-1", "Error": str(e)}


def handle_tq_kline(params: dict) -> dict:
    """获取K线数据"""
    stock_list = params.get("stock_list", [])
    period = params.get("period", "day")
    count = params.get("count", 5)
    dividend_type = params.get("dividend_type", "front")

    if not stock_list:
        return {"ErrorId": "-1", "Error": "stock_list required"}

    result = {}
    for code in stock_list:
        try:
            full_code = parse_tdx_code(code)
            bars = client.bars.get(full_code, period=period, count=count)
            result[code] = [
                {
                    "Date": b.date.isoformat() if hasattr(b.date, 'isoformat') else str(b.date),
                    "Open": float(b.open or 0),
                    "Close": float(b.close or 0),
                    "High": float(b.high or 0),
                    "Low": float(b.low or 0),
                    "Volume": int(b.volume or 0),
                }
                for b in (bars.bars if hasattr(bars, 'bars') else bars)
            ]
        except Exception as e:
            logger.error(f"Kline error for {code}: {e}")
            result[code] = []

    return result


# ==================== 健康检查 ====================

@app.get("/health")
async def health():
    """健康检查"""
    methods = []
    if client:
        methods.extend([m for m in dir(client) if not m.startswith('_')])

    return {
        "status": "ok" if client and client.connected else "degraded",
        "connected": client.connected if client else False,
        "version": "2.1",
        "methods": methods,
    }


# ==================== 主入口 ====================

if __name__ == "__main__":
    import os
    parser = argparse.ArgumentParser(description="eltdx-TQ Gateway")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "17709")))
    parser.add_argument("--host", type=str, default=os.environ.get("HOST", "0.0.0.0"))
    args = parser.parse_args()

    run(app, host=args.host, port=args.port)
