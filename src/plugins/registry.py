"""Plugin registry for registration and discovery."""

from __future__ import annotations
import asyncio, re, time
from datetime import datetime
from typing import Any
import structlog
from .models import (
    Plugin,
    PluginCreateRequest,
    PluginEvent,
    PluginStatus,
    PluginTestResult,
    PluginType,
    PluginUpdateRequest,
)
from .transform import PayloadTransformer
from .webhook import WebhookExecutor

logger = structlog.get_logger()


class PluginNotFoundError(Exception):
    pass


class PluginExistsError(Exception):
    pass


class PluginRegistry:
    def __init__(self):
        self._plugins: dict[str, Plugin] = {}
        self._webhook_executor = WebhookExecutor()
        self._transformer = PayloadTransformer()
        self._lock = asyncio.Lock()

    async def register(self, request: PluginCreateRequest) -> Plugin:
        async with self._lock:
            if request.id in self._plugins:
                raise PluginExistsError(f"Plugin '{request.id}' already exists")
            if request.type == PluginType.WEBHOOK and not request.webhook_config:
                raise ValueError("Webhook plugins require webhook_config")
            if request.type == PluginType.ENRICHMENT and not request.enrichment_config:
                raise ValueError("Enrichment plugins require enrichment_config")
            if request.type == PluginType.FILTER and not request.filter_config:
                raise ValueError("Filter plugins require filter_config")
            plugin = Plugin(
                id=request.id,
                name=request.name,
                description=request.description,
                type=request.type,
                events=request.events,
                priority=request.priority,
                webhook_config=request.webhook_config,
                enrichment_config=request.enrichment_config,
                filter_config=request.filter_config,
            )
            self._plugins[plugin.id] = plugin
            return plugin

    async def update(self, plugin_id: str, request: PluginUpdateRequest) -> Plugin:
        async with self._lock:
            if plugin_id not in self._plugins:
                raise PluginNotFoundError(f"Plugin '{plugin_id}' not found")
            plugin = self._plugins[plugin_id]
            for k, v in request.model_dump(exclude_none=True).items():
                setattr(plugin, k, v)
            plugin.updated_at = datetime.utcnow()
            return plugin

    async def unregister(self, plugin_id: str) -> None:
        async with self._lock:
            if plugin_id not in self._plugins:
                raise PluginNotFoundError(f"Plugin '{plugin_id}' not found")
            del self._plugins[plugin_id]

    def get(self, plugin_id: str) -> Plugin:
        if plugin_id not in self._plugins:
            raise PluginNotFoundError(f"Plugin '{plugin_id}' not found")
        return self._plugins[plugin_id]

    def list(
        self,
        plugin_type: PluginType | None = None,
        status: PluginStatus | None = None,
        event: PluginEvent | None = None,
    ) -> list[Plugin]:
        plugins = list(self._plugins.values())
        if plugin_type:
            plugins = [p for p in plugins if p.type == plugin_type]
        if status:
            plugins = [p for p in plugins if p.status == status]
        if event:
            plugins = [p for p in plugins if event in p.events]
        return sorted(plugins, key=lambda p: p.priority)

    def get_plugins_for_event(self, event: PluginEvent) -> list[Plugin]:
        return [p for p in self.list(event=event) if p.status == PluginStatus.ACTIVE]

    async def execute_all(
        self, event: PluginEvent, data: dict[str, Any], parallel: bool = True
    ) -> dict[str, PluginTestResult]:
        plugins = self.get_plugins_for_event(event)
        if not plugins:
            return {}
        results: dict[str, PluginTestResult] = {}
        if parallel:
            tasks = [self._execute_plugin(p, event, data) for p in plugins]
            for plugin, result in zip(
                plugins, await asyncio.gather(*tasks, return_exceptions=True)
            ):
                results[plugin.id] = (
                    result
                    if not isinstance(result, Exception)
                    else PluginTestResult(
                        success=False,
                        plugin_id=plugin.id,
                        plugin_type=plugin.type,
                        execution_time_ms=0,
                        error=str(result),
                    )
                )
        else:
            for plugin in plugins:
                try:
                    results[plugin.id] = await self._execute_plugin(plugin, event, data)
                except Exception as e:
                    results[plugin.id] = PluginTestResult(
                        success=False,
                        plugin_id=plugin.id,
                        plugin_type=plugin.type,
                        execution_time_ms=0,
                        error=str(e),
                    )
        return results

    async def _execute_plugin(
        self, plugin: Plugin, event: PluginEvent, data: dict[str, Any]
    ) -> PluginTestResult:
        start = time.monotonic()
        if plugin.type == PluginType.WEBHOOK:
            result = await self._execute_webhook(plugin, event, data)
        elif plugin.type == PluginType.ENRICHMENT:
            result = await self._execute_enrichment(plugin, data)
        elif plugin.type == PluginType.FILTER:
            result = await self._execute_filter(plugin, data)
        else:
            raise ValueError(f"Unknown plugin type: {plugin.type}")
        result.execution_time_ms = int((time.monotonic() - start) * 1000)
        self._update_metrics(
            plugin, result.success, result.execution_time_ms, result.error
        )
        return result

    async def _execute_webhook(
        self, plugin: Plugin, event: PluginEvent, data: dict[str, Any]
    ) -> PluginTestResult:
        config = plugin.webhook_config
        if not config:
            raise ValueError(f"Plugin {plugin.id} missing webhook_config")
        payload = (
            self._transformer.transform(
                config.payload_template, data, event=event.value, plugin_id=plugin.id
            )
            if config.payload_template
            else (
                {
                    "event": event.value,
                    "plugin_id": plugin.id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "data": data,
                }
                if config.include_full_card
                else {
                    "event": event.value,
                    "plugin_id": plugin.id,
                    "incident_id": data.get("incident_id"),
                }
            )
        )
        delivery = await self._webhook_executor.send(
            url=config.url,
            method=config.method,
            payload=payload,
            headers=config.headers,
            timeout_ms=config.timeout_ms,
            retry_config=config.retry,
            hmac_config=config.hmac,
            plugin_id=plugin.id,
            event=event,
        )
        return PluginTestResult(
            success=delivery.success,
            plugin_id=plugin.id,
            plugin_type=PluginType.WEBHOOK,
            execution_time_ms=delivery.latency_ms,
            request_payload=payload,
            response=(
                {"status": delivery.response_status}
                if delivery.response_status
                else None
            ),
            error=delivery.error,
            details={"attempts": delivery.attempt_number, "url": config.url},
        )

    async def _execute_enrichment(
        self, plugin: Plugin, data: dict[str, Any]
    ) -> PluginTestResult:
        config = plugin.enrichment_config
        if not config:
            raise ValueError(f"Plugin {plugin.id} missing enrichment_config")
        import aiohttp

        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=config.timeout_ms / 1000)
            ) as session:
                async with session.request(
                    method=config.method, url=config.url, headers=config.headers
                ) as resp:
                    return PluginTestResult(
                        success=resp.status < 400,
                        plugin_id=plugin.id,
                        plugin_type=PluginType.ENRICHMENT,
                        execution_time_ms=0,
                        response={"status": resp.status},
                        details={"target_field": config.target_field},
                    )
        except Exception as e:
            return PluginTestResult(
                success=False,
                plugin_id=plugin.id,
                plugin_type=PluginType.ENRICHMENT,
                execution_time_ms=0,
                error=str(e),
            )

    async def _execute_filter(
        self, plugin: Plugin, data: dict[str, Any]
    ) -> PluginTestResult:
        config = plugin.filter_config
        if not config:
            raise ValueError(f"Plugin {plugin.id} missing filter_config")
        matches = self._evaluate_conditions(config.conditions, data, config.match_mode)
        result_data, action_taken = data.copy(), "none"
        if matches:
            if config.action == "exclude":
                action_taken = "excluded"
            elif config.action == "modify":
                for field, value in config.modifications.items():
                    result_data[field] = value
                action_taken = "modified"
            else:
                action_taken = "included"
        return PluginTestResult(
            success=True,
            plugin_id=plugin.id,
            plugin_type=PluginType.FILTER,
            execution_time_ms=0,
            details={
                "conditions_matched": matches,
                "action": config.action,
                "action_taken": action_taken,
                "result_data": result_data if config.action == "modify" else None,
            },
        )

    def _evaluate_conditions(
        self, conditions: list, data: dict[str, Any], match_mode: str
    ) -> bool:
        if not conditions:
            return True

        def get_field(d, path):
            for p in path.split("."):
                d = d.get(p) if isinstance(d, dict) else None
            return d

        results = []
        for c in conditions:
            v = get_field(data, c.field)
            op = c.operator
            exp = c.value
            if op == "eq":
                r = v == exp
            elif op == "ne":
                r = v != exp
            elif op == "in":
                r = v in exp
            elif op == "not_in":
                r = v not in exp
            elif op == "contains":
                r = exp in str(v) if v else False
            elif op == "matches":
                r = bool(re.match(exp, str(v))) if v else False
            elif op == "gt":
                r = v > exp if v is not None else False
            elif op == "lt":
                r = v < exp if v is not None else False
            elif op == "gte":
                r = v >= exp if v is not None else False
            elif op == "lte":
                r = v <= exp if v is not None else False
            else:
                r = False
            results.append(r)
        return all(results) if match_mode == "all" else any(results)

    def _update_metrics(
        self, plugin: Plugin, success: bool, latency_ms: int, error: str | None = None
    ) -> None:
        m = plugin.metrics
        m.total_executions += 1
        m.last_execution_at = datetime.utcnow()
        if success:
            m.successful_executions += 1
            m.consecutive_failures = 0
        else:
            m.failed_executions += 1
            m.consecutive_failures += 1
            m.last_error = error
            if m.consecutive_failures >= plugin.max_consecutive_failures:
                plugin.status = PluginStatus.ERROR
        m.avg_latency_ms = (
            (m.avg_latency_ms * (m.total_executions - 1) + latency_ms)
            / m.total_executions
            if m.total_executions > 1
            else float(latency_ms)
        )

    async def test_plugin(
        self, plugin_id: str, sample_data: dict[str, Any], dry_run: bool = True
    ) -> PluginTestResult:
        plugin = self.get(plugin_id)
        event = plugin.events[0] if plugin.events else PluginEvent.CONTEXT_ASSEMBLED
        if dry_run and plugin.type == PluginType.WEBHOOK:
            config = plugin.webhook_config
            payload = (
                self._transformer.transform(
                    config.payload_template,
                    sample_data,
                    event=event.value,
                    plugin_id=plugin.id,
                )
                if config and config.payload_template
                else {"event": event.value, "plugin_id": plugin.id, "data": sample_data}
            )
            return PluginTestResult(
                success=True,
                plugin_id=plugin_id,
                plugin_type=plugin.type,
                execution_time_ms=0,
                request_payload=payload,
                details={"dry_run": True, "url": config.url if config else None},
            )
        return await self._execute_plugin(plugin, event, sample_data)


_registry: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry
