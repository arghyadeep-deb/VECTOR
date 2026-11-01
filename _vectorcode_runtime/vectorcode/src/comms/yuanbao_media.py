"""Yuanbao media handler — COS upload, TIM media message building."""

import hashlib
import hmac
import os
import time
from typing import Any, Optional

from loguru import logger

try:
    import httpx
    _HTTPX = True
except ImportError:
    _HTTPX = False

COS_BUCKET = "cos.ap-guangzhou.myqcloud.com"

async def upload_image(image_path: str, api_domain: str = "yuanbao.tencent.com",
                       app_id: str = "", app_secret: str = "") -> Optional[str]:
    """Upload image to COS and return URL."""
    if not _HTTPX: return None
    async with httpx.AsyncClient() as c:
        ts = str(int(time.time()))
        sig = hmac.new(app_secret.encode(), (ts + app_id).encode(), hashlib.sha256).hexdigest()
        r = await c.post(f"https://{api_domain}/api/resource/genUploadInfo",
                        json={"app_id": app_id, "timestamp": ts, "sign": sig,
                              "file_type": "image", "file_name": os.path.basename(image_path)})
        data = r.json()
        if data.get("code") != 0: return None
        upload_info = data.get("data", {})
        with open(image_path, "rb") as f:
            cos_url = f"https://{upload_info.get('bucket', COS_BUCKET)}{upload_info.get('path', '')}"
            upload_response = await c.put(cos_url, data=f, headers={
                "Authorization": _build_cos_auth(upload_info, "PUT"),
                "x-cos-security-token": upload_info.get("sessionToken", ""),
            })
            if upload_response.status_code >= 300:
                logger.warning(
                    "Yuanbao COS upload failed with status {}",
                    upload_response.status_code,
                )
                return None
        return upload_info.get("url")

def _build_cos_auth(upload_info: dict, method: str = "PUT") -> str:
    """Build COS HMAC-SHA1 authorization header."""
    skey = upload_info.get("tmpSecretKey", "")
    skid = upload_info.get("tmpSecretId", "")
    path = upload_info.get("path", "/")
    sign = hmac.new(skey.encode(), f"{method}\n{path}\n\n".encode(), hashlib.sha1).digest()
    return f"q-sign-algorithm=sha1&q-ak={skid}&q-sign-time=&q-key-time=&q-header-list=&q-url-param-list=&q-signature={sign.hex()}"

async def upload_file(file_path: str, api_domain: str = "yuanbao.tencent.com",
                      app_id: str = "", app_secret: str = "") -> Optional[str]:
    """Upload a file to COS."""
    return await upload_image(file_path, api_domain, app_id, app_secret)
