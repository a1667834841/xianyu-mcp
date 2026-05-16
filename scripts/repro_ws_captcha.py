#!/usr/bin/env python3
"""Reproduce WebSocket accessToken captcha/risk responses without auto-solving."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api.http_client import HttpClient


API = "mtop.taobao.idlemessage.pc.login.token"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, help="Directory containing auth.json or token.json")
    parser.add_argument("--device-id", default="manual_repro", help="Device ID to use for accessToken requests")
    parser.add_argument("--iterations", type=int, default=30, help="How many attempts to run")
    parser.add_argument("--sleep", type=float, default=0.2, help="Delay between attempts in seconds")
    args = parser.parse_args()

    os.environ["XIANYU_DATA_DIR"] = args.data_dir
    client = HttpClient()
    request_data = {
        "appKey": "444e9908a51d1cb236a27862abc769c9",
        "deviceId": args.device_id,
    }

    for attempt in range(1, args.iterations + 1):
        started_at = time.time()
        response = await client._send_request(API, request_data, retry_on_captcha=False)
        need_captcha = client._need_captcha(response)
        payload = {
            "attempt": attempt,
            "elapsed_ms": int((time.time() - started_at) * 1000),
            "need_captcha": need_captcha,
            "need_relogin": client._need_relogin(response),
            "ret": response.get("ret"),
            "has_access_token": bool(response.get("data", {}).get("accessToken")),
            "url": response.get("data", {}).get("url", ""),
        }
        print(json.dumps(payload, ensure_ascii=False))
        if need_captcha:
            return 2
        await asyncio.sleep(args.sleep)

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
