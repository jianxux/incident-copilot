"""Plugin framework for extensible integrations."""
from .models import EnrichmentConfig, FilterConfig, Plugin, PluginEvent, PluginStatus, PluginType, WebhookConfig
from .registry import PluginRegistry, get_registry
from .transform import PayloadTransformer
from .webhook import WebhookExecutor
__all__ = ["Plugin", "PluginType", "PluginStatus", "PluginEvent", "WebhookConfig", "EnrichmentConfig", "FilterConfig", "PluginRegistry", "WebhookExecutor", "PayloadTransformer", "get_registry"]
