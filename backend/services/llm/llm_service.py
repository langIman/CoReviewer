from collections.abc import AsyncGenerator

import httpx
import json
import logging

from fastapi import HTTPException

from backend.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL

logger = logging.getLogger(__name__)


async def call_qwen(system_prompt: str, user_prompt: str) -> str:
    """调用千问 API（非流式），返回完整文本。"""
    if not QWEN_API_KEY:
        raise HTTPException(status_code=500, detail="未配置 QWEN_API_KEY 环境变量")

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
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            logger.error("LLM API error %d: %s", resp.status_code, resp.text[:500])
            raise HTTPException(
                status_code=502,
                detail=f"LLM API 错误 ({resp.status_code}): {resp.text[:200]}",
            )
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def stream_qwen(system_prompt: str, user_prompt: str) -> AsyncGenerator[str, None]:
    """调用千问 API（OpenAI 兼容格式），流式返回文本片段。"""
    if not QWEN_API_KEY:
        raise HTTPException(status_code=500, detail="未配置 QWEN_API_KEY 环境变量")

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
                logger.error("LLM stream error %d: %s", resp.status_code, body.decode()[:500])
                raise HTTPException(
                    status_code=502,
                    detail=f"LLM API 错误 ({resp.status_code}): {body.decode()[:200]}",
                )

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
                    logger.debug("SSE chunk parse skipped: %s", data[:100])
                    continue


async def call_llm(
    messages: list[dict],
    tools: list[dict] | None = None,
    timeout: float = 120.0,
) -> dict:
    """支持完整消息历史 + 工具定义的 LLM 调用。

    返回完整的 choice message dict，可能包含 content 和/或 tool_calls。
    """
    if not QWEN_API_KEY:
        raise HTTPException(status_code=500, detail="未配置 QWEN_API_KEY 环境变量")

    url = f"{QWEN_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {QWEN_API_KEY}",
        "Content-Type": "application/json",
    }
    payload: dict = {
        "model": QWEN_MODEL,
        "messages": messages,
        "stream": False,
    }

    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            logger.error("LLM API error %d: %s", resp.status_code, resp.text[:500])
            raise HTTPException(
                status_code=502,
                detail=f"LLM API 错误 ({resp.status_code}): {resp.text[:200]}",
            )
        data = resp.json()
        return data["choices"][0]["message"]
