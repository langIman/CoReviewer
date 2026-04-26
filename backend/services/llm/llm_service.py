from collections.abc import AsyncGenerator

import httpx
import json
import logging

from fastapi import HTTPException

from backend.config import (
    QWEN_API_KEY,
    QWEN_BASE_URL,
    QWEN_ENABLE_THINKING,
    QWEN_MODEL,
)

logger = logging.getLogger(__name__)


def _model_supports_thinking_switch(model: str) -> bool:
    normalized = model.strip().lower()
    return normalized.startswith("qwen3") or normalized.startswith("qwq")


def _apply_qwen_options(payload: dict, enable_thinking: bool | None = None) -> None:
    """注入 qwen3 系列的 enable_thinking 开关。

    优先级：调用点显式参数 > QWEN_ENABLE_THINKING 环境变量 > 模型默认。
    非 qwen3/qwq 模型上忽略，避免 dashscope 报错。
    """
    effective = enable_thinking if enable_thinking is not None else QWEN_ENABLE_THINKING
    if effective is None:
        return
    if _model_supports_thinking_switch(QWEN_MODEL):
        payload["enable_thinking"] = effective


async def call_qwen(
    system_prompt: str,
    user_prompt: str,
    enable_thinking: bool | None = None,
) -> str:
    """调用千问 API（非流式），返回完整文本。

    enable_thinking: qwen3 系列默认开 CoT，TTFT 高数倍。模板化任务（文档生成、
    摘要等）建议显式传 False；判断/推理类任务保持 None（走 env / 模型默认）。
    """
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
    _apply_qwen_options(payload, enable_thinking)

    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            logger.error("LLM API error %d: %s", resp.status_code, resp.text[:500])
            raise HTTPException(
                status_code=502,
                detail=f"LLM API 错误 ({resp.status_code}): {resp.text[:200]}",
            )
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def stream_qwen(
    system_prompt: str,
    user_prompt: str,
    enable_thinking: bool | None = None,
) -> AsyncGenerator[str, None]:
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
    _apply_qwen_options(payload, enable_thinking)

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


async def stream_messages(
    messages: list[dict],
    timeout: float = 120.0,
    enable_thinking: bool | None = None,
) -> AsyncGenerator[str, None]:
    """流式版 call_llm：接完整 messages 历史，逐 token 产出 content。

    对比 ``stream_qwen(system, user)``：那个只能接两段字符串，无法承载
    QAContextBuilder 装配出的完整 messages。本函数与 ``call_llm`` 对称。
    不返回 tool_calls（快速模式不跑工具循环）。
    """
    if not QWEN_API_KEY:
        raise HTTPException(status_code=500, detail="未配置 QWEN_API_KEY 环境变量")

    url = f"{QWEN_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {QWEN_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": QWEN_MODEL,
        "messages": messages,
        "stream": True,
    }
    _apply_qwen_options(payload, enable_thinking)

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                logger.error(
                    "LLM stream error %d: %s", resp.status_code, body.decode()[:500]
                )
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
    enable_thinking: bool | None = None,
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
    _apply_qwen_options(payload, enable_thinking)

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
