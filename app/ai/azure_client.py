"""The single model-provider boundary: Azure OpenAI only."""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from app.config import Settings

T = TypeVar("T", bound=BaseModel)


class AzureClientError(RuntimeError):
    """Base class for model boundary failures."""


class AzureConfigurationError(AzureClientError):
    pass


class AzureResponseError(AzureClientError):
    pass


@dataclass(frozen=True)
class ModelUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    deployment: str


class ToolProposal(BaseModel):
    name: str
    arguments: dict[str, Any]


def _strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Adapt Pydantic JSON Schema to Azure strict structured-output rules."""
    schema = model.model_json_schema()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("default", None)
            properties = node.get("properties")
            if node.get("type") == "object":
                if not isinstance(properties, dict):
                    properties = {}
                    node["properties"] = properties
                node["additionalProperties"] = False
                node["required"] = list(properties)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)
    return schema


class JsonModelClient(Protocol):
    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        response_model: type[T],
        project_id: str,
        task_id: str | None = None,
    ) -> tuple[T, ModelUsage]: ...

    async def propose_tools(
        self,
        *,
        system: str,
        user: str,
        tools: list[dict[str, Any]],
        project_id: str,
        task_id: str | None = None,
    ) -> tuple[list[ToolProposal], ModelUsage]: ...


class AzureOpenAIClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.azure_openai_endpoint or not settings.azure_openai_api_key:
            raise AzureConfigurationError(
                "AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY are required; "
                "Azure OpenAI is the only supported model provider"
            )
        if not settings.azure_openai_deployment:
            raise AzureConfigurationError("AZURE_OPENAI_DEPLOYMENT is required")
        try:
            from openai import AsyncAzureOpenAI
        except ImportError as error:
            raise AzureConfigurationError("the official openai package is required") from error
        self.settings = settings
        self._client = AsyncAzureOpenAI(
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            azure_endpoint=settings.azure_openai_endpoint,
            timeout=settings.request_timeout_seconds,
            max_retries=0,
        )

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        response_model: type[T],
        project_id: str,
        task_id: str | None = None,
    ) -> tuple[T, ModelUsage]:
        del project_id, task_id
        started = time.perf_counter()
        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                response = await self._client.chat.completions.create(  # type: ignore[call-overload]
                    model=self.settings.azure_openai_deployment,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": response_model.__name__.lower(),
                            "strict": True,
                            "schema": _strict_json_schema(response_model),
                        },
                    },
                    max_completion_tokens=self.settings.max_task_tokens,
                )
                content = response.choices[0].message.content
                if not content:
                    raise AzureResponseError("Azure OpenAI returned an empty response")
                try:
                    parsed = response_model.model_validate(json.loads(content))
                except (ValueError, TypeError) as error:
                    raise AzureResponseError(
                        "Azure OpenAI returned invalid structured JSON"
                    ) from error
                usage_data = response.usage
                usage = ModelUsage(
                    prompt_tokens=int(getattr(usage_data, "prompt_tokens", 0) or 0),
                    completion_tokens=int(getattr(usage_data, "completion_tokens", 0) or 0),
                    total_tokens=int(getattr(usage_data, "total_tokens", 0) or 0),
                    latency_ms=(time.perf_counter() - started) * 1000,
                    deployment=self.settings.azure_openai_deployment or "",
                )
                return parsed, usage
            except AzureResponseError:
                raise
            except Exception as error:  # noqa: BLE001 - provider failures need bounded retry handling
                last_error = error
                if attempt >= self.settings.max_retries:
                    break
                await asyncio.sleep(min(8.0, (2**attempt) * 0.25 + secrets.randbelow(200) / 1000))
        raise AzureClientError("Azure OpenAI request failed after bounded retries") from last_error

    async def propose_tools(self, *, system: str, user: str, tools: list[dict[str, Any]],
                            project_id: str, task_id: str | None = None) -> tuple[list[ToolProposal], ModelUsage]:
        """Request tool proposals without executing them.

        The returned proposals remain untrusted until passed to ToolGateway.
        """
        del project_id, task_id
        started = time.perf_counter()
        response_tools: list[dict[str, Any]] = []
        for tool in tools:
            function = tool.get("function", {})
            response_tools.append({
                "type": "function",
                "name": function["name"],
                "description": function.get("description", ""),
                "parameters": function.get("parameters", {}),
                "strict": True,
            })
        try:
            response = await self._client.responses.create(  # type: ignore[call-overload]
                model=self.settings.azure_openai_deployment,
                instructions=system,
                input=user,
                tools=response_tools,
                tool_choice="required",
                parallel_tool_calls=True,
                max_output_tokens=self.settings.max_task_tokens,
            )
        except Exception as error:
            raise AzureClientError("Azure OpenAI tool-calling request failed") from error
        usage_data = response.usage
        usage = ModelUsage(
            prompt_tokens=int(getattr(usage_data, "input_tokens", 0) or 0),
            completion_tokens=int(getattr(usage_data, "output_tokens", 0) or 0),
            total_tokens=int(getattr(usage_data, "total_tokens", 0) or 0),
            latency_ms=(time.perf_counter() - started) * 1000,
            deployment=self.settings.azure_openai_deployment or "",
        )
        proposals: list[ToolProposal] = []
        for call in getattr(response, "output", []):
            if getattr(call, "type", None) != "function_call":
                continue
            try:
                arguments = json.loads(call.arguments)
            except (TypeError, ValueError) as error:
                raise AzureResponseError("Azure OpenAI returned invalid tool arguments") from error
            if not isinstance(arguments, dict):
                raise AzureResponseError("Azure OpenAI tool arguments must be an object")
            proposals.append(ToolProposal(name=call.name, arguments=arguments))
        return proposals, usage
