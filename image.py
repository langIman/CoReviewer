from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import sys
import time
from pathlib import Path

from openai import APIStatusError, OpenAI, OpenAIError


DEFAULT_PROMPT = "在中国互联网公司，一个计算机实习生在现代办公室里写代码，人漏出少一点，要求真实感，画面整体覆上一层轻微模糊，不要局部清晰局部模糊"


def _log(message: str, prefix: str = "") -> None:
    print(f"{prefix}{message}", flush=True)


def _ensure_ascii_header(value: str, source: str) -> str:
    try:
        value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise RuntimeError(
            f"{source} contains non-ASCII characters. HTTP auth headers must be ASCII."
        ) from exc
    return value


def _read_toml_string(text: str, key: str, section: str | None = None) -> str | None:
    if section:
        match = re.search(rf"(?ms)^\[{re.escape(section)}\]\s*(.*?)(?=^\[|\Z)", text)
        if not match:
            return None
        text = match.group(1)

    match = re.search(rf'(?m)^{re.escape(key)}\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else None


def load_codex_openai_settings() -> tuple[str, str, str]:
    """Reuse the OpenAI-compatible provider settings that Codex already uses."""
    config_text = ""
    config_path = Path.home() / ".codex" / "config.toml"
    if config_path.exists():
        config_text = config_path.read_text(encoding="utf-8")

    api_key = os.getenv("OPENAI_API_KEY")
    api_key_source = "OPENAI_API_KEY"
    if api_key:
        api_key = _ensure_ascii_header(api_key.strip(), api_key_source)
    else:
        auth_path = Path.home() / ".codex" / "auth.json"
        if auth_path.exists():
            api_key = json.loads(auth_path.read_text(encoding="utf-8")).get("OPENAI_API_KEY")
            api_key_source = str(auth_path)
            if api_key:
                api_key = _ensure_ascii_header(api_key.strip(), api_key_source)

    base_url = (
        os.getenv("OPENAI_BASE_URL")
        or _read_toml_string(config_text, "base_url", "model_providers.OpenAI")
    )
    text_model = (
        os.getenv("IMAGE_TEXT_MODEL")
        or os.getenv("OPENAI_MODEL")
        or _read_toml_string(config_text, "model")
    )

    missing = [
        name
        for name, value in {
            "OPENAI_API_KEY": api_key,
            "OPENAI_BASE_URL": base_url,
            "OPENAI_MODEL": text_model,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing required setting(s): {', '.join(missing)}")

    return api_key, base_url, text_model


def generate_image(
    prompt: str,
    output_path: Path,
    *,
    image_model: str = "gpt-image-2",
    size: str = "1024x1024",
    quality: str = "low",
    output_format: str = "png",
    request_timeout: float = 130.0,
    wait_timeout: float = 600.0,
    poll_interval: float = 5.0,
    mode: str = "stream",
    partial_images: int = 2,
    verbose: bool = False,
    log_prefix: str = "",
) -> str:
    api_key, base_url, text_model = load_codex_openai_settings()
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=request_timeout)
    image_tool = {
        "type": "image_generation",
        "model": image_model,
        "size": size,
        "quality": quality,
        "output_format": output_format,
    }
    if mode == "stream" and partial_images > 0:
        image_tool["partial_images"] = partial_images

    if verbose:
        _log(f"Base URL: {base_url}", log_prefix)
        _log(f"Text model: {text_model}", log_prefix)
        _log(f"Image model: {image_model}", log_prefix)
        _log(f"Output: {output_path}", log_prefix)
        _log(f"Mode: {mode}", log_prefix)
        if mode == "stream":
            _log("Opening streaming image generation request...", log_prefix)
        elif mode == "background":
            _log("Creating background image generation task...", log_prefix)
        else:
            _log("Sending image generation request. This can take 20-60 seconds...", log_prefix)

    if mode == "stream":
        return generate_image_streaming(
            client,
            text_model,
            prompt,
            output_path,
            image_tool=image_tool,
            image_model=image_model,
            verbose=verbose,
            log_prefix=log_prefix,
        )

    started_at = time.monotonic()
    response = client.responses.create(
        model=text_model,
        background=(mode == "background"),
        input=prompt,
        tools=[image_tool],
        **({} if mode == "background" else {"store": False}),
    )
    if verbose:
        elapsed = time.monotonic() - started_at
        _log(f"Initial response after {elapsed:.1f}s: {response.id} status={response.status}", log_prefix)

    if mode == "background":
        response = wait_for_response(
            client,
            response.id,
            wait_timeout=wait_timeout,
            poll_interval=poll_interval,
            verbose=verbose,
            log_prefix=log_prefix,
        )
    elif verbose:
        _log("Response received. Decoding image...", log_prefix)

    if response.status != "completed":
        detail = response.error or response.incomplete_details
        raise RuntimeError(f"Response {response.id} ended with status={response.status}: {detail}")

    output_path.write_bytes(base64.b64decode(image_b64_from_response(response)))
    return response.id


def image_b64_from_response(response) -> str:
    image_calls = [
        item
        for item in response.output or []
        if getattr(item, "type", None) == "image_generation_call"
    ]
    if not image_calls or not getattr(image_calls[0], "result", None):
        output_types = [getattr(item, "type", None) for item in response.output or []]
        raise RuntimeError(f"No image returned. Response output types: {output_types}")
    return image_calls[0].result


def generate_image_streaming(
    client: OpenAI,
    text_model: str,
    prompt: str,
    output_path: Path,
    *,
    image_tool: dict,
    image_model: str,
    verbose: bool = False,
    log_prefix: str = "",
) -> str:
    started_at = time.monotonic()
    response_id = None
    final_response = None
    image_b64 = None

    stream = client.responses.create(
        model=text_model,
        input=prompt,
        tools=[image_tool],
        stream=True,
        store=False,
    )

    for event in stream:
        event_type = getattr(event, "type", "")

        response = getattr(event, "response", None)
        if response is not None:
            response_id = response.id

        item = getattr(event, "item", None)
        if item is not None and getattr(item, "type", None) == "image_generation_call":
            response_id = response_id or getattr(item, "id", None)
            if getattr(item, "result", None):
                image_b64 = item.result

        if event_type == "response.image_generation_call.partial_image":
            image_b64 = event.partial_image_b64
            if verbose:
                elapsed = time.monotonic() - started_at
                _log(f"Partial image {event.partial_image_index} received after {elapsed:.1f}s", log_prefix)
        elif verbose and event_type in {
            "response.created",
            "response.in_progress",
            "response.image_generation_call.in_progress",
            "response.image_generation_call.generating",
            "response.image_generation_call.completed",
            "response.output_item.done",
        }:
            elapsed = time.monotonic() - started_at
            details = ""
            if item is not None:
                details = (
                    f" item={getattr(item, 'type', None)}"
                    f" status={getattr(item, 'status', None)}"
                    f" has_result={bool(getattr(item, 'result', None))}"
                )
            _log(f"Stream event after {elapsed:.1f}s: {event_type}{details}", log_prefix)

        if event_type == "response.completed":
            final_response = event.response
            response_id = final_response.id
            try:
                image_b64 = image_b64_from_response(final_response)
            except RuntimeError:
                if image_b64 is None:
                    raise
                if verbose:
                    _log("Completed response had no final image; using latest streamed image.", log_prefix)
        elif event_type == "response.failed":
            raise RuntimeError(f"Response failed: {event.response.error}")

    if not image_b64:
        if final_response is not None:
            image_b64 = image_b64_from_response(final_response)
        else:
            raise RuntimeError("Streaming ended without an image result")

    output_path.write_bytes(base64.b64decode(image_b64))
    return response_id or f"{image_model}:stream"


def wait_for_response(
    client: OpenAI,
    response_id: str,
    *,
    wait_timeout: float,
    poll_interval: float,
    verbose: bool = False,
    log_prefix: str = "",
):
    deadline = time.monotonic() + wait_timeout
    last_status = None

    while True:
        response = client.responses.retrieve(response_id)
        status = response.status

        if verbose and status != last_status:
            elapsed = wait_timeout - max(0, deadline - time.monotonic())
            _log(f"Polling {response_id}: status={status} after {elapsed:.1f}s", log_prefix)
            last_status = status

        if status in {"completed", "failed", "cancelled", "incomplete"}:
            if verbose and status == "completed":
                _log("Background response completed. Decoding image...", log_prefix)
            return response

        if time.monotonic() >= deadline:
            raise RuntimeError(f"Timed out waiting for response {response_id} after {wait_timeout:.0f}s")

        time.sleep(poll_interval)


def output_path_for_index(output_path: Path, index: int, count: int) -> Path:
    if count == 1:
        return output_path

    suffix = output_path.suffix or ".png"
    stem = output_path.stem if output_path.suffix else output_path.name
    width = max(2, len(str(count)))
    return output_path.with_name(f"{stem}_{index:0{width}d}{suffix}")


def generate_images_batch(
    prompt: str,
    output_path: Path,
    *,
    count: int,
    workers: int,
    image_model: str,
    size: str,
    quality: str,
    output_format: str,
    request_timeout: float,
    wait_timeout: float,
    poll_interval: float,
    mode: str,
    partial_images: int,
) -> tuple[list[tuple[int, Path, str]], list[tuple[int, Path, BaseException]]]:
    workers = min(max(1, workers), count)
    successes: list[tuple[int, Path, str]] = []
    failures: list[tuple[int, Path, BaseException]] = []

    _log(f"Generating {count} image(s) with {workers} worker(s)...")
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_job = {}
        for index in range(1, count + 1):
            path = output_path_for_index(output_path, index, count)
            prefix = f"[{index}/{count}] "
            _log(f"Queued {path}", prefix)
            future = executor.submit(
                generate_image,
                prompt,
                path,
                image_model=image_model,
                size=size,
                quality=quality,
                output_format=output_format,
                request_timeout=request_timeout,
                wait_timeout=wait_timeout,
                poll_interval=poll_interval,
                mode=mode,
                partial_images=partial_images,
                verbose=True,
                log_prefix=prefix,
            )
            future_to_job[future] = (index, path)

        for future in as_completed(future_to_job):
            index, path = future_to_job[future]
            prefix = f"[{index}/{count}] "
            try:
                response_id = future.result()
            except BaseException as exc:
                failures.append((index, path, exc))
                _log(f"FAILED {path}: {exc}", prefix)
            else:
                successes.append((index, path, response_id))
                _log(f"Wrote {path} ({response_id})", prefix)

    successes.sort(key=lambda item: item[0])
    failures.sort(key=lambda item: item[0])
    return successes, failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an image with gpt-image-2 via Responses API.")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--output", default="test.png")
    parser.add_argument("--count", default=int(os.getenv("IMAGE_COUNT", "1")), type=int)
    parser.add_argument("--workers", default=int(os.getenv("IMAGE_WORKERS", "1")), type=int)
    parser.add_argument("--image-model", default=os.getenv("IMAGE_MODEL", "gpt-image-2"))
    parser.add_argument("--size", default=os.getenv("IMAGE_SIZE", "1024x1024"))
    parser.add_argument("--quality", default=os.getenv("IMAGE_QUALITY", "low"))
    parser.add_argument("--format", default=os.getenv("IMAGE_FORMAT", "png"), dest="output_format")
    parser.add_argument("--request-timeout", default=float(os.getenv("IMAGE_REQUEST_TIMEOUT", "130")), type=float)
    parser.add_argument("--wait-timeout", default=float(os.getenv("IMAGE_WAIT_TIMEOUT", "600")), type=float)
    parser.add_argument("--poll-interval", default=float(os.getenv("IMAGE_POLL_INTERVAL", "5")), type=float)
    parser.add_argument("--mode", choices=["stream", "background", "sync"], default=os.getenv("IMAGE_MODE", "stream"))
    parser.add_argument("--partial-images", default=int(os.getenv("IMAGE_PARTIAL_IMAGES", "2")), type=int)
    parser.add_argument("--no-background", action="store_true", help="Deprecated alias for --mode sync.")
    parser.add_argument(
        "--timeout",
        type=float,
        help="Deprecated alias for --wait-timeout. Kept for old commands.",
    )
    args = parser.parse_args()
    wait_timeout = args.timeout if args.timeout is not None else args.wait_timeout
    if args.count < 1:
        print("--count must be >= 1", file=sys.stderr, flush=True)
        raise SystemExit(1)
    if args.workers < 1:
        print("--workers must be >= 1", file=sys.stderr, flush=True)
        raise SystemExit(1)

    if args.count > 1:
        successes, failures = generate_images_batch(
            args.prompt,
            Path(args.output),
            count=args.count,
            workers=args.workers,
            image_model=args.image_model,
            size=args.size,
            quality=args.quality,
            output_format=args.output_format,
            request_timeout=args.request_timeout,
            wait_timeout=wait_timeout,
            poll_interval=args.poll_interval,
            mode="sync" if args.no_background else args.mode,
            partial_images=args.partial_images,
        )
        _log(f"Done: {len(successes)} succeeded, {len(failures)} failed.")
        if failures:
            raise SystemExit(1)
        return

    try:
        response_id = generate_image(
            args.prompt,
            Path(args.output),
            image_model=args.image_model,
            size=args.size,
            quality=args.quality,
            output_format=args.output_format,
            request_timeout=args.request_timeout,
            wait_timeout=wait_timeout,
            poll_interval=args.poll_interval,
            mode="sync" if args.no_background else args.mode,
            partial_images=args.partial_images,
            verbose=True,
        )
    except APIStatusError as exc:
        body = exc.response.text[:500] if exc.response is not None else ""
        print(f"API error {exc.status_code}: {body}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
    except (OpenAIError, RuntimeError) as exc:
        print(f"Image generation failed: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc

    _log(f"Wrote {args.output} using {args.image_model} ({response_id})")


if __name__ == "__main__":
    main()
