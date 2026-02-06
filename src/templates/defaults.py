"""Built-in incident response templates."""

import structlog

from .models import IncidentTemplate, TemplateCategory, TemplateStep
from .store import template_store

logger = structlog.get_logger()


def _create_step(
    order: int,
    title: str,
    description: str | None = None,
    suggested_action: str | None = None,
    time_estimate_minutes: int | None = None,
    runbook_url: str | None = None,
    is_critical: bool = False,
    tags: list[str] | None = None,
) -> TemplateStep:
    """Helper to create a template step."""
    return TemplateStep(
        id=f"step-{order}",
        order=order,
        title=title,
        description=description,
        suggested_action=suggested_action,
        time_estimate_minutes=time_estimate_minutes,
        runbook_url=runbook_url,
        is_critical=is_critical,
        tags=tags or [],
    )


# --- Built-in Templates ---


DATABASE_OUTAGE_TEMPLATE = IncidentTemplate(
    id="builtin-database-outage",
    name="Database Outage",
    description="Response checklist for database connectivity issues, failovers, and outages",
    category=TemplateCategory.DATABASE,
    is_builtin=True,
    keywords=["database", "db", "mysql", "postgres", "connection", "outage", "down", "unavailable", "pool", "exhausted"],
    service_tags=["database", "db", "mysql", "postgres", "rds", "aurora"],
    severity_levels=["critical", "high"],
    steps=[
        _create_step(
            1,
            "Verify database connectivity",
            "Check if the database is reachable from application servers",
            "mysql -h {{db_host}} -u {{db_user}} -p -e 'SELECT 1'",
            5,
            is_critical=True,
        ),
        _create_step(
            2,
            "Check database metrics",
            "Review CPU, memory, connections, and IOPS in monitoring dashboard",
            None,
            3,
        ),
        _create_step(
            3,
            "Review active connections",
            "Check for connection pool exhaustion or runaway queries",
            "SHOW PROCESSLIST;",
            5,
        ),
        _create_step(
            4,
            "Check for long-running queries",
            "Identify and potentially kill blocking queries",
            "SELECT * FROM information_schema.processlist WHERE TIME > 60;",
            5,
        ),
        _create_step(
            5,
            "Check replication status",
            "Verify replication lag and slave status",
            "SHOW SLAVE STATUS\\G",
            3,
        ),
        _create_step(
            6,
            "Review recent changes",
            "Check for recent deployments, schema changes, or config updates",
            None,
            5,
        ),
        _create_step(
            7,
            "Consider failover",
            "If primary is unrecoverable, initiate failover to replica",
            None,
            10,
            is_critical=True,
        ),
        _create_step(
            8,
            "Notify stakeholders",
            "Update status page and notify affected teams",
            None,
            5,
        ),
    ],
)


API_DEGRADATION_TEMPLATE = IncidentTemplate(
    id="builtin-api-degradation",
    name="API Service Degradation",
    description="Response checklist for API latency, errors, and performance issues",
    category=TemplateCategory.APPLICATION,
    is_builtin=True,
    keywords=["api", "latency", "slow", "timeout", "5xx", "500", "502", "503", "error", "degradation", "performance"],
    service_tags=["api", "service", "backend", "gateway"],
    severity_levels=["critical", "high", "medium"],
    steps=[
        _create_step(
            1,
            "Check error rates and latency",
            "Review APM dashboard for error rates and p99 latency",
            None,
            3,
            is_critical=True,
        ),
        _create_step(
            2,
            "Identify affected endpoints",
            "Determine which API endpoints are impacted",
            None,
            5,
        ),
        _create_step(
            3,
            "Check application logs",
            "Look for exceptions, stack traces, and error patterns",
            "kubectl logs -l app={{service_name}} --tail=100",
            5,
        ),
        _create_step(
            4,
            "Check downstream dependencies",
            "Verify databases, caches, and external services are healthy",
            None,
            5,
        ),
        _create_step(
            5,
            "Review recent deployments",
            "Check if a recent deploy correlates with the issue",
            "kubectl rollout history deployment/{{service_name}}",
            3,
        ),
        _create_step(
            6,
            "Consider rollback",
            "If recent deploy is the cause, initiate rollback",
            "kubectl rollout undo deployment/{{service_name}}",
            5,
            is_critical=True,
        ),
        _create_step(
            7,
            "Scale if needed",
            "Increase replicas if under resource pressure",
            "kubectl scale deployment/{{service_name}} --replicas=10",
            3,
        ),
        _create_step(
            8,
            "Enable circuit breaker",
            "If a dependency is failing, enable circuit breaker to fail fast",
            None,
            5,
        ),
    ],
)


MEMORY_LEAK_TEMPLATE = IncidentTemplate(
    id="builtin-memory-leak",
    name="Memory Leak Investigation",
    description="Response checklist for OOM errors and memory leak detection",
    category=TemplateCategory.APPLICATION,
    is_builtin=True,
    keywords=["memory", "leak", "oom", "out of memory", "heap", "gc", "garbage collection", "killed"],
    service_tags=["java", "node", "python", "application"],
    severity_levels=["critical", "high"],
    steps=[
        _create_step(
            1,
            "Identify affected pods/instances",
            "Find which instances are experiencing memory issues",
            "kubectl top pods -l app={{service_name}}",
            3,
            is_critical=True,
        ),
        _create_step(
            2,
            "Check for OOM kills",
            "Review container restart reasons",
            "kubectl describe pod {{pod_name}} | grep -A 5 'Last State'",
            3,
        ),
        _create_step(
            3,
            "Capture heap dump",
            "If possible, capture heap dump for analysis",
            "jcmd {{pid}} GC.heap_dump /tmp/heapdump.hprof",
            10,
        ),
        _create_step(
            4,
            "Review memory trends",
            "Check memory usage graphs for steady increase pattern",
            None,
            5,
        ),
        _create_step(
            5,
            "Check for recent code changes",
            "Review recent commits for memory-related changes",
            None,
            5,
        ),
        _create_step(
            6,
            "Restart affected instances",
            "Rolling restart to temporarily mitigate",
            "kubectl rollout restart deployment/{{service_name}}",
            5,
        ),
        _create_step(
            7,
            "Increase memory limits",
            "Temporary workaround: increase container memory limits",
            None,
            5,
        ),
        _create_step(
            8,
            "Analyze heap dump",
            "Use MAT or similar tool to identify leak source",
            None,
            30,
        ),
    ],
)


HIGH_CPU_TEMPLATE = IncidentTemplate(
    id="builtin-high-cpu",
    name="High CPU Usage",
    description="Response checklist for CPU spikes and sustained high utilization",
    category=TemplateCategory.INFRASTRUCTURE,
    is_builtin=True,
    keywords=["cpu", "high", "spike", "utilization", "100%", "throttling", "slow"],
    service_tags=["compute", "server", "instance", "container"],
    severity_levels=["high", "medium"],
    steps=[
        _create_step(
            1,
            "Identify high CPU processes",
            "Find processes consuming the most CPU",
            "top -b -n 1 | head -20",
            3,
            is_critical=True,
        ),
        _create_step(
            2,
            "Check for CPU throttling",
            "Verify if containers are being throttled",
            "kubectl top pods -l app={{service_name}}",
            3,
        ),
        _create_step(
            3,
            "Capture thread dump",
            "Get thread dump to identify hot spots",
            "jstack {{pid}} > /tmp/thread_dump.txt",
            5,
        ),
        _create_step(
            4,
            "Check for runaway processes",
            "Look for infinite loops or expensive operations",
            None,
            5,
        ),
        _create_step(
            5,
            "Review request patterns",
            "Check if traffic spike is causing the issue",
            None,
            5,
        ),
        _create_step(
            6,
            "Scale horizontally",
            "Add more instances to distribute load",
            "kubectl scale deployment/{{service_name}} --replicas=10",
            5,
        ),
        _create_step(
            7,
            "Enable rate limiting",
            "Protect the service with rate limiting if under attack",
            None,
            5,
        ),
    ],
)


DISK_FULL_TEMPLATE = IncidentTemplate(
    id="builtin-disk-full",
    name="Disk Space Exhaustion",
    description="Response checklist for disk full and storage issues",
    category=TemplateCategory.INFRASTRUCTURE,
    is_builtin=True,
    keywords=["disk", "full", "storage", "space", "no space left", "inode", "volume"],
    service_tags=["storage", "disk", "volume", "pvc"],
    severity_levels=["critical", "high"],
    steps=[
        _create_step(
            1,
            "Check disk usage",
            "Identify which filesystems are full",
            "df -h",
            2,
            is_critical=True,
        ),
        _create_step(
            2,
            "Find large files",
            "Locate largest files consuming space",
            "du -sh /* | sort -rh | head -20",
            5,
        ),
        _create_step(
            3,
            "Check log files",
            "Logs are often the culprit",
            "du -sh /var/log/*",
            3,
        ),
        _create_step(
            4,
            "Clean old logs",
            "Remove or compress old log files",
            "find /var/log -name '*.log' -mtime +7 -delete",
            5,
        ),
        _create_step(
            5,
            "Check for core dumps",
            "Remove old core dump files",
            "find / -name 'core.*' -type f -delete",
            5,
        ),
        _create_step(
            6,
            "Check Docker images",
            "Clean unused Docker images if applicable",
            "docker system prune -af",
            5,
        ),
        _create_step(
            7,
            "Expand volume",
            "If cleanup insufficient, expand the volume",
            None,
            15,
        ),
    ],
)


NETWORK_CONNECTIVITY_TEMPLATE = IncidentTemplate(
    id="builtin-network-connectivity",
    name="Network Connectivity Issues",
    description="Response checklist for network outages, DNS issues, and connectivity problems",
    category=TemplateCategory.NETWORK,
    is_builtin=True,
    keywords=["network", "dns", "connectivity", "timeout", "unreachable", "connection refused", "latency"],
    service_tags=["network", "dns", "loadbalancer", "vpc"],
    severity_levels=["critical", "high"],
    steps=[
        _create_step(
            1,
            "Test basic connectivity",
            "Verify network reachability",
            "ping {{target_host}}",
            2,
            is_critical=True,
        ),
        _create_step(
            2,
            "Check DNS resolution",
            "Verify DNS is resolving correctly",
            "nslookup {{target_host}}",
            2,
        ),
        _create_step(
            3,
            "Trace network path",
            "Identify where packets are being dropped",
            "traceroute {{target_host}}",
            5,
        ),
        _create_step(
            4,
            "Check firewall rules",
            "Verify security groups and firewall rules",
            None,
            5,
        ),
        _create_step(
            5,
            "Check load balancer health",
            "Verify load balancer targets are healthy",
            None,
            5,
        ),
        _create_step(
            6,
            "Review VPC/network config",
            "Check route tables and network ACLs",
            None,
            10,
        ),
        _create_step(
            7,
            "Check for provider issues",
            "Review cloud provider status page",
            None,
            3,
        ),
    ],
)


SSL_CERTIFICATE_TEMPLATE = IncidentTemplate(
    id="builtin-ssl-certificate",
    name="SSL/TLS Certificate Issues",
    description="Response checklist for certificate expiration and SSL errors",
    category=TemplateCategory.SECURITY,
    is_builtin=True,
    keywords=["ssl", "tls", "certificate", "expired", "cert", "https", "handshake", "x509"],
    service_tags=["certificate", "ssl", "tls", "ingress"],
    severity_levels=["critical", "high"],
    steps=[
        _create_step(
            1,
            "Check certificate expiration",
            "Verify certificate validity dates",
            "echo | openssl s_client -connect {{host}}:443 2>/dev/null | openssl x509 -noout -dates",
            2,
            is_critical=True,
        ),
        _create_step(
            2,
            "Verify certificate chain",
            "Check if full certificate chain is valid",
            "openssl s_client -connect {{host}}:443 -showcerts",
            3,
        ),
        _create_step(
            3,
            "Check certificate domains",
            "Verify certificate covers the correct domains",
            "openssl s_client -connect {{host}}:443 2>/dev/null | openssl x509 -noout -text | grep DNS",
            3,
        ),
        _create_step(
            4,
            "Renew certificate",
            "If expired, trigger certificate renewal",
            "certbot renew --cert-name {{domain}}",
            10,
            is_critical=True,
        ),
        _create_step(
            5,
            "Update certificate in secrets",
            "Deploy new certificate to Kubernetes",
            "kubectl create secret tls {{secret_name}} --cert=cert.pem --key=key.pem --dry-run=client -o yaml | kubectl apply -f -",
            5,
        ),
        _create_step(
            6,
            "Reload ingress/load balancer",
            "Trigger reload to pick up new certificate",
            "kubectl rollout restart deployment/ingress-nginx-controller",
            5,
        ),
    ],
)


KUBERNETES_POD_CRASH_TEMPLATE = IncidentTemplate(
    id="builtin-k8s-pod-crash",
    name="Kubernetes Pod Crash Loop",
    description="Response checklist for CrashLoopBackOff and pod failure issues",
    category=TemplateCategory.INFRASTRUCTURE,
    is_builtin=True,
    keywords=["kubernetes", "k8s", "pod", "crash", "crashloopbackoff", "restart", "failed", "oomkilled"],
    service_tags=["kubernetes", "k8s", "pod", "deployment"],
    severity_levels=["critical", "high"],
    steps=[
        _create_step(
            1,
            "Get pod status",
            "Check current state and restart count",
            "kubectl get pods -l app={{service_name}} -o wide",
            2,
            is_critical=True,
        ),
        _create_step(
            2,
            "Describe pod events",
            "Review pod events for failure reasons",
            "kubectl describe pod {{pod_name}}",
            3,
        ),
        _create_step(
            3,
            "Check pod logs",
            "Review logs for crash cause",
            "kubectl logs {{pod_name}} --previous",
            5,
        ),
        _create_step(
            4,
            "Check resource limits",
            "Verify pod isn't hitting resource limits",
            "kubectl top pod {{pod_name}}",
            3,
        ),
        _create_step(
            5,
            "Verify liveness/readiness probes",
            "Check if probes are configured correctly",
            "kubectl get deployment {{deployment_name}} -o yaml | grep -A 10 'livenessProbe\\|readinessProbe'",
            5,
        ),
        _create_step(
            6,
            "Check image pull issues",
            "Verify container image is accessible",
            "kubectl describe pod {{pod_name}} | grep -A 5 'Events'",
            3,
        ),
        _create_step(
            7,
            "Roll back deployment",
            "If caused by recent deploy, roll back",
            "kubectl rollout undo deployment/{{deployment_name}}",
            5,
            is_critical=True,
        ),
    ],
)


SECURITY_BREACH_TEMPLATE = IncidentTemplate(
    id="builtin-security-breach",
    name="Security Incident Response",
    description="Response checklist for security breaches, unauthorized access, and attacks",
    category=TemplateCategory.SECURITY,
    is_builtin=True,
    keywords=["security", "breach", "attack", "unauthorized", "intrusion", "compromised", "hack", "ddos"],
    service_tags=["security", "auth", "identity"],
    severity_levels=["critical"],
    steps=[
        _create_step(
            1,
            "Assess and contain",
            "Quickly assess scope and contain the breach",
            None,
            10,
            is_critical=True,
        ),
        _create_step(
            2,
            "Preserve evidence",
            "Capture logs and forensic data before any changes",
            None,
            15,
            is_critical=True,
        ),
        _create_step(
            3,
            "Revoke compromised credentials",
            "Immediately rotate any compromised keys/tokens",
            None,
            10,
            is_critical=True,
        ),
        _create_step(
            4,
            "Isolate affected systems",
            "Network isolate compromised systems",
            None,
            10,
        ),
        _create_step(
            5,
            "Review access logs",
            "Analyze logs for unauthorized access patterns",
            None,
            30,
        ),
        _create_step(
            6,
            "Notify security team",
            "Escalate to security team and leadership",
            None,
            5,
            is_critical=True,
        ),
        _create_step(
            7,
            "Check for lateral movement",
            "Verify other systems haven't been compromised",
            None,
            30,
        ),
        _create_step(
            8,
            "Document timeline",
            "Create detailed incident timeline",
            None,
            15,
        ),
        _create_step(
            9,
            "Regulatory notification",
            "Determine if regulatory notification required",
            None,
            10,
        ),
    ],
)


CACHE_FAILURE_TEMPLATE = IncidentTemplate(
    id="builtin-cache-failure",
    name="Cache Service Failure",
    description="Response checklist for Redis, Memcached, and caching layer issues",
    category=TemplateCategory.DATABASE,
    is_builtin=True,
    keywords=["cache", "redis", "memcached", "miss", "eviction", "memory", "cluster"],
    service_tags=["redis", "memcached", "cache", "elasticache"],
    severity_levels=["high", "medium"],
    steps=[
        _create_step(
            1,
            "Check cache connectivity",
            "Verify cache is reachable",
            "redis-cli -h {{cache_host}} ping",
            2,
            is_critical=True,
        ),
        _create_step(
            2,
            "Check cache memory usage",
            "Review memory utilization",
            "redis-cli -h {{cache_host}} INFO memory",
            3,
        ),
        _create_step(
            3,
            "Check eviction rate",
            "High evictions indicate memory pressure",
            "redis-cli -h {{cache_host}} INFO stats | grep evicted",
            3,
        ),
        _create_step(
            4,
            "Review slow log",
            "Check for slow operations",
            "redis-cli -h {{cache_host}} SLOWLOG GET 10",
            5,
        ),
        _create_step(
            5,
            "Check cluster health",
            "If clustered, verify cluster state",
            "redis-cli -h {{cache_host}} CLUSTER INFO",
            5,
        ),
        _create_step(
            6,
            "Enable cache fallback",
            "Configure application to handle cache misses gracefully",
            None,
            10,
        ),
        _create_step(
            7,
            "Scale cache cluster",
            "Add nodes if capacity is the issue",
            None,
            15,
        ),
    ],
)


MESSAGE_QUEUE_TEMPLATE = IncidentTemplate(
    id="builtin-message-queue",
    name="Message Queue Backlog",
    description="Response checklist for Kafka, RabbitMQ, and SQS queue issues",
    category=TemplateCategory.APPLICATION,
    is_builtin=True,
    keywords=["queue", "kafka", "rabbitmq", "sqs", "backlog", "lag", "consumer", "producer", "message"],
    service_tags=["kafka", "rabbitmq", "sqs", "queue", "messaging"],
    severity_levels=["high", "medium"],
    steps=[
        _create_step(
            1,
            "Check queue depth",
            "Measure message backlog size",
            None,
            3,
            is_critical=True,
        ),
        _create_step(
            2,
            "Check consumer lag",
            "For Kafka, check consumer group lag",
            "kafka-consumer-groups --bootstrap-server {{broker}} --describe --group {{consumer_group}}",
            5,
        ),
        _create_step(
            3,
            "Verify consumer health",
            "Check if consumers are running and processing",
            None,
            5,
        ),
        _create_step(
            4,
            "Check for poison messages",
            "Look for messages causing consumer failures",
            None,
            10,
        ),
        _create_step(
            5,
            "Scale consumers",
            "Add more consumer instances",
            "kubectl scale deployment/{{consumer_deployment}} --replicas=10",
            5,
        ),
        _create_step(
            6,
            "Check producer rate",
            "Verify if producers are overwhelming consumers",
            None,
            5,
        ),
        _create_step(
            7,
            "Enable dead letter queue",
            "Route failing messages to DLQ for investigation",
            None,
            10,
        ),
    ],
)


THIRD_PARTY_OUTAGE_TEMPLATE = IncidentTemplate(
    id="builtin-third-party-outage",
    name="Third-Party Service Outage",
    description="Response checklist when external dependencies are unavailable",
    category=TemplateCategory.APPLICATION,
    is_builtin=True,
    keywords=["third party", "vendor", "external", "dependency", "outage", "upstream", "downstream"],
    service_tags=["integration", "external", "vendor"],
    severity_levels=["critical", "high"],
    steps=[
        _create_step(
            1,
            "Confirm third-party status",
            "Check vendor status page and support channels",
            None,
            5,
            is_critical=True,
        ),
        _create_step(
            2,
            "Assess impact",
            "Determine which features are affected",
            None,
            10,
        ),
        _create_step(
            3,
            "Enable fallback/degraded mode",
            "Switch to backup provider or graceful degradation",
            None,
            15,
            is_critical=True,
        ),
        _create_step(
            4,
            "Update error handling",
            "Ensure appropriate error messages for users",
            None,
            10,
        ),
        _create_step(
            5,
            "Contact vendor support",
            "Open ticket with vendor if needed",
            None,
            10,
        ),
        _create_step(
            6,
            "Monitor for recovery",
            "Set up alerts for when service recovers",
            None,
            5,
        ),
        _create_step(
            7,
            "Document for postmortem",
            "Note impact and response for later review",
            None,
            10,
        ),
    ],
)


# List of all built-in templates
DEFAULT_TEMPLATES = [
    DATABASE_OUTAGE_TEMPLATE,
    API_DEGRADATION_TEMPLATE,
    MEMORY_LEAK_TEMPLATE,
    HIGH_CPU_TEMPLATE,
    DISK_FULL_TEMPLATE,
    NETWORK_CONNECTIVITY_TEMPLATE,
    SSL_CERTIFICATE_TEMPLATE,
    KUBERNETES_POD_CRASH_TEMPLATE,
    SECURITY_BREACH_TEMPLATE,
    CACHE_FAILURE_TEMPLATE,
    MESSAGE_QUEUE_TEMPLATE,
    THIRD_PARTY_OUTAGE_TEMPLATE,
]


async def initialize_default_templates() -> int:
    """
    Initialize the built-in default templates.
    
    Returns:
        Number of templates initialized
    """
    initialized = 0
    
    for template in DEFAULT_TEMPLATES:
        existing = await template_store.get(template.id)
        if not existing:
            await template_store.save(template)
            initialized += 1
            logger.info(
                "default_template_initialized",
                template_id=template.id,
                name=template.name,
            )
    
    logger.info(
        "default_templates_initialization_complete",
        total_templates=len(DEFAULT_TEMPLATES),
        newly_initialized=initialized,
    )
    
    return initialized
