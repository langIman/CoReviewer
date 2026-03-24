from collections.abc import AsyncGenerator

import httpx
import json

from backend.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL


async def stream_qwen(system_prompt: str, user_prompt: str) -> AsyncGenerator[str, None]:
    """调用千问 API（OpenAI 兼容格式），流式返回文本片段。"""
    if not QWEN_API_KEY:
        yield "错误：未配置 QWEN_API_KEY 环境变量。请设置后重启后端。"
        return

    url = f"{QWEN_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {QWEN_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": QWEN_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": True,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                yield f"LLM API 错误 ({resp.status_code}): {body.decode()}"
                return

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
