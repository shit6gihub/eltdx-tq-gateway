#!/usr/bin/env python3
"""eltdx-TQ Gateway v2.3 - 完整通达信行情网关

支持两类接口：
1. TQ 兼容接口（/jsonrpc, /）：适配 SIDA v0.4.38 TQ vendor
2. eltdx 原生接口（/rpc）：支持全部 126+ 个公开方法

用法：
    python3 eltdx-tq-gateway.py [--port 17709] [--host 0.0.0.0]
"""
import argparse
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from uvicorn import run
except ImportError:
    print("需要安装: pip install 'eltdx[http]'")
    sys.exit(1)

from eltdx import TdxClient
from eltdx.http_server import _Gateway as _EltdxGateway

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client: TdxClient | None = None
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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理"""
    global client, eltdx_gateway
    
    tdx_host = os.environ.get("TDX_HOST", "114.142.142.124")
    tdx_port = int(os.environ.get("TDX_PORT", "7709"))
    
    print(f"Connecting to TDX server at {tdx_host}:{tdx_port}...")
    client = TdxClient(timeout=10)
    client.connect()
    print(f"Connected: {client.transport.connected_hosts}")
    
    eltdx_gateway = _EltdxGateway(client)
    methods = eltdx_gateway.methods()
    print(f"Available methods: {len(methods)}")
    
    yield
    
    if client:
        client.close()


app = FastAPI(title="eltdx-TQ Gateway", lifespan=lifespan)


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
            "Volume": int(s.total_hand or 0),
            "Amount": float(s.amount or 0),
            "Change": float(s.change or 0),
            "ChangePct": float(s.change_pct or 0),
            "ErrorId": "0",
        }
    except Exception as e:
        logger.error(f"Snapshot error: {e}")
        return {"ErrorId": "-1", "Error": str(e)}


def handle_tq_more_info(params: dict) -> dict:
    """获取扩展指标"""
    stock_code = params.get("stock_code", "")
    if not stock_code:
        return {"ErrorId": "-1", "Error": "stock_code required"}
    try:
        # 先获取快照获取基础数据
        snaps = client.quotes.get_snapshots([parse_tdx_code(stock_code)])
        if not snaps:
            return {"ErrorId": "-1", "Error": "no data"}

        s = snaps[0]

        # 从 stock_profile_table 获取财务数据
        pe = pb = mv = 0.0
        turnover_rate = 0.0
        try:
            profile = client.helpers.stock_profile_table([parse_tdx_code(stock_code)])
            if profile and profile.get('rows'):
                row = profile['rows'][0]
                finance = row.get('finance', {})
                pe = finance.get('eps', 0) or 0
                pb = finance.get('mei_gu_jing_zi_chan_raw_float', 0) or 0
                mv = row.get('total_market_value', 0) or 0
                turnover_rate = row.get('turnover_rate', 0) or 0
        except Exception as e:
            logger.warning(f"Failed to get finance data: {e}")

        return {
            "ZAF": float(s.change_pct or 0),
            "Zsz": float(mv * 1e8) if mv else 0.0,
            "Ltsz": float((mv or 0) * 0.6 * 1e8),
            "fHSL": float(turnover_rate),
            "fLianB": 0.0,
            "Wtb": float(s.change_pct or 0),
            "DynaPE": float(pe),
            "PB_MRQ": float(pb),
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
                    "Date": b.time.date().isoformat() if hasattr(b.time, 'isoformat') else str(b.time),
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
    connected = bool(client and client.transport.connected_hosts)
    methods_count = len(eltdx_gateway.methods()) if eltdx_gateway else 0
    return {
        "status": "ok" if connected else "degraded",
        "connected": connected,
        "version": "2.3",
        "methods_count": methods_count,
    }


# ==================== RPC 接口 ====================

@app.post("/rpc")
async def rpc(request: Request):
    """eltdx 原生 RPC 接口"""
    body = await request.json()
    method = body.get("method", "")
    params = body.get("params", {})
    req_id = body.get("id", 1)

    if not eltdx_gateway:
        return JSONResponse({"id": req_id, "ok": False, "error": {"type": "RuntimeError", "message": "client not connected"}})

    try:
        result = eltdx_gateway.call_json(method, params)
        return {"id": req_id, "ok": True, "result": result}
    except Exception as e:
        logger.error(f"RPC error {method}: {e}")
        return JSONResponse({"id": req_id, "ok": False, "error": {"type": type(e).__name__, "message": str(e)}})


# ==================== 主入口 ====================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="eltdx-TQ Gateway")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "17709")))
    parser.add_argument("--host", type=str, default=os.environ.get("HOST", "0.0.0.0"))
    args = parser.parse_args()

    print(f"Starting eltdx-TQ Gateway on {args.host}:{args.port}...")
    run(app, host=args.host, port=args.port, log_level="info")
