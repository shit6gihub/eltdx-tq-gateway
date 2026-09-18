#!/usr/bin/env python3
"""eltdx-TQ Gateway: 完整通达信行情网关

支持两类接口：
1. TQ 兼容接口（/jsonrpc, /）：适配 SIDA v0.4.38 TQ vendor
2. eltdx 原生接口（/rpc）：支持全部 126 个公开方法

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
    print("需要安装: pip install 'eltdx[http]''")
    sys.exit(1)

from eltdx import TdxClient
from eltdx.http_server import _Gateway as _EltdxGateway

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="eltdx-TQ Gateway")
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
            "Volume": int(s.current_hand or 0),
            "Amount": float(s.amount or 0),
            "Inside": int(s.inside_dish or 0),
            "Outside": int(s.outer_disc or 0),
            "ErrorId": "0",
        }
    except Exception as e:
        logger.error(f"snapshot failed: {e}")
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
        # 尝试从 helpers 获取更多信息
        try:
            profile = client.f10.company_profile(stock_code[:6])
            pe = getattr(profile, 'pe_ratio', 0) or 0
            pb = getattr(profile, 'pb_ratio', 0) or 0
            mv = getattr(profile, 'market_value', 0) or 0
        except:
            pe = pb = mv = 0.0
        return {
            "ZAF": float(s.change_pct or 0),
            "Zsz": float(mv * 1e8),  # 总市值
            "Ltsz": float(mv * 0.6 * 1e8),  # 流通市值估算
            "fHSL": float(s.turnover_rate or 0),
            "fLianB": float(s.volume_ratio or 0),
            "Wtb": float(s.turnover_rate or 0),
            "DynaPE": float(pe),
            "PB_MRQ": float(pb),
            "ErrorId": "0",
        }
    except Exception as e:
        logger.error(f"more_info failed: {e}")
        return {"ErrorId": "-1", "Error": str(e)}


def handle_tq_kline(params: dict) -> dict:
    """获取 K 线数据"""
    stock_list = params.get("stock_list", [])
    period = params.get("period", "1d")
    count = int(params.get("count", 120))
    adjust = params.get("dividend_type", "front")
    adjust_map = {"front": "qfq", "back": "hfq", "none": "none"}
    adjust = adjust_map.get(adjust, "qfq")
    result = {}
    for tqc in stock_list:
        if not isinstance(tqc, str):
            continue
        try:
            bars = client.bars.get(parse_tdx_code(tqc), period=period, count=count, adjust=adjust)
            if bars and hasattr(bars, 'bars') and bars.bars:
                result[tqc] = {
                    "Date": [b.time.date().isoformat() for b in bars.bars],
                    "Open": [float(b.open) for b in bars.bars],
                    "Close": [float(b.close) for b in bars.bars],
                    "High": [float(b.high) for b in bars.bars],
                    "Low": [float(b.low) for b in bars.bars],
                    "Volume": [float(b.volume_lots) for b in bars.bars],
                }
            else:
                result[tqc] = {"ErrorId": "-1", "Error": "no bars"}
        except Exception as e:
            logger.error(f"kline failed {tqc}: {e}")
            result[tqc] = {"ErrorId": "-1", "Error": str(e)}
    return result


# ==================== eltdx 原生接口 ====================

@app.get("/health")
async def health():
    """健康检查"""
    return {
        "status": "ok",
        "connected": bool(client and client.transport.connected_hosts),
        "version": "2.0",
        "methods": eltdx_gateway.methods() if eltdx_gateway else []
    }


@app.get("/methods")
async def methods():
    """获取所有支持的方法列表"""
    if not eltdx_gateway:
        return {"methods": [], "error": "client not connected"}
    return {
        "methods": eltdx_gateway.methods(),
        "total": len(eltdx_gateway.methods()),
        "websocket_only": ["quotes.subscribe", "quotes.unsubscribe"]
    }


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


@app.get("/rpc")
async def rpc_get():
    return JSONResponse({"id": None, "ok": False, "error": {"type": "GatewayMethodError", "message": "Use POST for RPC calls"}})


# ==================== 主函数 ====================

def main():
    global client, eltdx_gateway
    parser = argparse.ArgumentParser(description="eltdx-TQ Gateway")
    parser.add_argument("--port", type=int, default=17709)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    args = parser.parse_args()

    print(f"Starting eltdx-TQ Gateway on {args.host}:{args.port}...")
    try:
        client = TdxClient(timeout=5)
        print(f"Connected: {client.transport.connected_hosts}")
        eltdx_gateway = _EltdxGateway(client)
        print(f"Available methods: {len(eltdx_gateway.methods())}")
    except Exception as e:
        print(f"Failed to connect: {e}")
        sys.exit(1)

    run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
