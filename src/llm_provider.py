"""
统一 LLM 提供商接口 — 支持 OpenAI 兼容 / Anthropic / Google 三大类 API。
通过 YAML 配置切换模型，每个 pipeline 阶段可绑定不同模型。
"""

import os
import re
import time
import asyncio
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置数据结构
# ---------------------------------------------------------------------------

@dataclass
class ProviderConfig:
    name: str
    type: str                     # openai_compatible | anthropic | google
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: int = 120


@dataclass
class Settings:
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    roles: dict[str, str] = field(default_factory=dict)
    pipeline: dict = field(default_factory=dict)
    ingestion: dict = field(default_factory=dict)
    humanizer: dict = field(default_factory=dict)
    output: dict = field(default_factory=dict)
    render: dict = field(default_factory=dict)

# ---------------------------------------------------------------------------
# 环境变量解析
# ---------------------------------------------------------------------------

_ENV_RE = re.compile(r"\$\{(\w+)\}")

def _resolve_env(value: str) -> str:
    if not isinstance(value, str):
        return value
    def _replace(m):
        return os.environ.get(m.group(1), "")
    return _ENV_RE.sub(_replace, value)

# ---------------------------------------------------------------------------
# 加载配置
# ---------------------------------------------------------------------------

def load_settings(config_path: str | Path = None) -> Settings:
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config" / "settings.yaml"
    config_path = Path(config_path)
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    providers = {}
    for name, cfg in raw.get("providers", {}).items():
        providers[name] = ProviderConfig(
            name=name,
            type=cfg.get("type", "openai_compatible"),
            api_key=_resolve_env(cfg.get("api_key", "")),
            base_url=_resolve_env(cfg.get("base_url", "")),
            model=_resolve_env(cfg.get("model", "")),
            max_tokens=cfg.get("max_tokens", 4096),
            temperature=cfg.get("temperature", 0.7),
            timeout=cfg.get("timeout", 120),
        )

    return Settings(
        providers=providers,
        roles=raw.get("roles", {}),
        pipeline=raw.get("pipeline", {}),
        ingestion=raw.get("ingestion", {}),
        humanizer=raw.get("humanizer", {}),
        output=raw.get("output", {}),
        render=raw.get("render", {}),
    )

# ---------------------------------------------------------------------------
# 统一 LLM 客户端
# ---------------------------------------------------------------------------

class LLMClient:
    """统一调用接口：根据角色自动路由到对应模型。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._clients: dict[str, object] = {}
        self._degraded = False

    @staticmethod
    def _is_upstream_unavailable(err: Exception) -> bool:
        msg = str(err).lower()
        keywords = [
            "504",
            "gateway time-out",
            "gateway timeout",
            "connection error",
            "connect timeout",
            "read timeout",
            "timed out",
            "service unavailable",
        ]
        return any(k in msg for k in keywords)

    def _get_provider(self, role: str) -> ProviderConfig:
        provider_name = self.settings.roles.get(role)
        if not provider_name or provider_name not in self.settings.providers:
            raise ValueError(f"角色 '{role}' 未配置有效的 provider，请检查 settings.yaml")
        return self.settings.providers[provider_name]

    def _get_openai_client(self, provider: ProviderConfig):
        key = f"openai_{provider.name}"
        if key not in self._clients:
            from openai import OpenAI
            self._clients[key] = OpenAI(
                api_key=provider.api_key,
                base_url=provider.base_url or None,
                timeout=provider.timeout,
            )
        return self._clients[key]

    def _get_async_openai_client(self, provider: ProviderConfig):
        key = f"async_openai_{provider.name}"
        if key not in self._clients:
            from openai import AsyncOpenAI
            self._clients[key] = AsyncOpenAI(
                api_key=provider.api_key,
                base_url=provider.base_url or None,
                timeout=provider.timeout,
            )
        return self._clients[key]

    def _get_anthropic_client(self, provider: ProviderConfig):
        key = f"anthropic_{provider.name}"
        if key not in self._clients:
            from anthropic import Anthropic
            self._clients[key] = Anthropic(api_key=provider.api_key)
        return self._clients[key]

    def _get_async_anthropic_client(self, provider: ProviderConfig):
        key = f"async_anthropic_{provider.name}"
        if key not in self._clients:
            from anthropic import AsyncAnthropic
            self._clients[key] = AsyncAnthropic(api_key=provider.api_key)
        return self._clients[key]

    def _get_google_client(self, provider: ProviderConfig):
        key = f"google_{provider.name}"
        if key not in self._clients:
            from google import genai
            self._clients[key] = genai.Client(api_key=provider.api_key)
        return self._clients[key]

    # ----- 同步调用 -----

    def call(
        self,
        role: str,
        messages: list[dict],
        *,
        temperature: float = None,
        max_tokens: int = None,
        system: str = None,
    ) -> str:
        if self._degraded:
            raise RuntimeError("LLM client degraded")
        provider = self._get_provider(role)
        max_retries = self.settings.pipeline.get("max_retry", 3)
        temp = temperature if temperature is not None else provider.temperature
        tokens = max_tokens if max_tokens is not None else provider.max_tokens

        for attempt in range(max_retries):
            try:
                if provider.type == "openai_compatible":
                    return self._call_openai(provider, messages, temp, tokens, system)
                elif provider.type == "anthropic":
                    return self._call_anthropic(provider, messages, temp, tokens, system)
                elif provider.type == "google":
                    return self._call_google(provider, messages, temp, tokens, system)
                else:
                    raise ValueError(f"不支持的 provider 类型: {provider.type}")
            except ValueError:
                raise
            except Exception as e:
                if self._is_upstream_unavailable(e):
                    self._degraded = True
                    raise RuntimeError(f"上游服务暂不可用: {e}") from e
                if attempt == max_retries - 1:
                    raise
                wait = 2 ** attempt
                logger.warning(f"API 调用失败 (尝试 {attempt+1}/{max_retries}): {e}. {wait}s 后重试...")
                time.sleep(wait)
        return ""

    def _call_openai(self, p: ProviderConfig, messages, temp, tokens, system) -> str:
        client = self._get_openai_client(p)
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        resp = client.chat.completions.create(
            model=p.model, messages=msgs,
            temperature=temp, max_tokens=tokens,
        )
        return resp.choices[0].message.content

    def _call_anthropic(self, p: ProviderConfig, messages, temp, tokens, system) -> str:
        client = self._get_anthropic_client(p)
        kwargs = dict(model=p.model, messages=messages, temperature=temp, max_tokens=tokens)
        if system:
            kwargs["system"] = system
        resp = client.messages.create(**kwargs)
        return resp.content[0].text

    def _call_google(self, p: ProviderConfig, messages, temp, tokens, system) -> str:
        client = self._get_google_client(p)
        contents = []
        if system:
            contents.append(system)
        for m in messages:
            contents.append(m["content"])
        resp = client.models.generate_content(
            model=p.model,
            contents=contents,
            config={
                "temperature": temp,
                "max_output_tokens": tokens,
            },
        )
        return resp.text

    # ----- 异步调用 -----

    async def acall(
        self,
        role: str,
        messages: list[dict],
        *,
        temperature: float = None,
        max_tokens: int = None,
        system: str = None,
    ) -> str:
        if self._degraded:
            raise RuntimeError("LLM client degraded")
        provider = self._get_provider(role)
        max_retries = self.settings.pipeline.get("max_retry", 3)
        temp = temperature if temperature is not None else provider.temperature
        tokens = max_tokens if max_tokens is not None else provider.max_tokens

        for attempt in range(max_retries):
            try:
                if provider.type == "openai_compatible":
                    return await self._acall_openai(provider, messages, temp, tokens, system)
                elif provider.type == "anthropic":
                    return await self._acall_anthropic(provider, messages, temp, tokens, system)
                elif provider.type == "google":
                    return await asyncio.get_event_loop().run_in_executor(
                        None, self._call_google, provider, messages, temp, tokens, system
                    )
                else:
                    raise ValueError(f"不支持的 provider 类型: {provider.type}")
            except ValueError:
                raise
            except Exception as e:
                if self._is_upstream_unavailable(e):
                    self._degraded = True
                    raise RuntimeError(f"上游服务暂不可用: {e}") from e
                if attempt == max_retries - 1:
                    raise
                wait = 2 ** attempt
                logger.warning(f"Async API 调用失败 (尝试 {attempt+1}/{max_retries}): {e}. {wait}s 后重试...")
                await asyncio.sleep(wait)
        return ""

    async def _acall_openai(self, p, messages, temp, tokens, system) -> str:
        client = self._get_async_openai_client(p)
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        resp = await client.chat.completions.create(
            model=p.model, messages=msgs,
            temperature=temp, max_tokens=tokens,
        )
        return resp.choices[0].message.content

    async def _acall_anthropic(self, p, messages, temp, tokens, system) -> str:
        client = self._get_async_anthropic_client(p)
        kwargs = dict(model=p.model, messages=messages, temperature=temp, max_tokens=tokens)
        if system:
            kwargs["system"] = system
        resp = await client.messages.create(**kwargs)
        return resp.content[0].text
