"""
Incident Copilot CLI

Commands for validating configuration, testing integrations, and managing the service.
"""

import asyncio
import sys
from collections.abc import Callable
from enum import StrEnum

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

app = typer.Typer(
    name="incident-copilot",
    help="Incident Copilot CLI - Validate config, test integrations, and more.",
    add_completion=False,
)

console = Console()


class CheckStatus(StrEnum):
    """Status of a configuration check."""

    OK = "ok"
    WARN = "warn"
    ERROR = "error"
    SKIP = "skip"


def status_icon(status: CheckStatus) -> str:
    """Get the icon for a status."""
    icons = {
        CheckStatus.OK: "[green]✓[/green]",
        CheckStatus.WARN: "[yellow]⚠[/yellow]",
        CheckStatus.ERROR: "[red]✗[/red]",
        CheckStatus.SKIP: "[dim]○[/dim]",
    }
    return icons.get(status, "?")


@app.command()
def validate(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
):
    """
    Validate environment configuration.

    Checks all required environment variables and validates their format.
    """
    from ..config import get_settings

    rprint(Panel.fit("[bold blue]Incident Copilot Configuration Validator[/bold blue]"))
    rprint()

    try:
        settings = get_settings()
    except Exception as e:
        rprint(f"[red]Failed to load settings: {e}[/red]")
        raise typer.Exit(1)

    checks = []

    # PagerDuty checks
    checks.append(
        check_config(
            "PagerDuty API Key",
            settings.pagerduty_api_key,
            required=False,
            format_hint="Starts with 'u+' or is a valid API token",
        )
    )
    checks.append(
        check_config(
            "PagerDuty Webhook Secret",
            settings.pagerduty_webhook_secret,
            required=False,
            format_hint="32+ character signing secret",
        )
    )

    # Opsgenie checks
    checks.append(
        check_config(
            "Opsgenie API Key",
            getattr(settings, "opsgenie_api_key", None),
            required=False,
            format_hint="GenieKey from Opsgenie API integration",
        )
    )

    # GitHub checks
    checks.append(
        check_config(
            "GitHub Token",
            settings.github_token,
            required=True,
            format_hint="Personal access token (ghp_xxx) or fine-grained token",
            validator=lambda x: x.startswith("ghp_") or x.startswith("github_pat_"),
        )
    )
    checks.append(
        check_config(
            "GitHub Organization",
            settings.github_org,
            required=True,
            format_hint="GitHub org or username",
        )
    )

    # Log provider checks
    log_provider = getattr(settings, "log_provider", "datadog")
    checks.append(
        check_config(
            "Log Provider",
            log_provider,
            required=True,
            format_hint="'datadog' or 'cloudwatch'",
            validator=lambda x: x in ("datadog", "cloudwatch"),
        )
    )

    if log_provider == "datadog":
        checks.append(
            check_config(
                "Datadog API Key",
                settings.datadog_api_key,
                required=True,
                format_hint="32-character hex string",
                validator=lambda x: len(x) == 32,
            )
        )
        checks.append(
            check_config(
                "Datadog App Key",
                settings.datadog_app_key,
                required=True,
                format_hint="40-character hex string",
                validator=lambda x: len(x) == 40,
            )
        )
    else:
        checks.append(
            check_config(
                "AWS Region",
                getattr(settings, "aws_region", None),
                required=True,
                format_hint="AWS region (e.g., us-east-1)",
            )
        )

    # Slack checks
    checks.append(
        check_config(
            "Slack Bot Token",
            settings.slack_bot_token,
            required=True,
            format_hint="xoxb-xxx bot token",
            validator=lambda x: x.startswith("xoxb-"),
        )
    )
    checks.append(
        check_config(
            "Slack Default Channel",
            settings.slack_default_channel,
            required=True,
            format_hint="Channel ID (C0123...) or name (#incidents)",
        )
    )

    # AI checks
    checks.append(
        check_config(
            "Anthropic API Key",
            settings.anthropic_api_key,
            required=True,
            format_hint="sk-ant-xxx",
            validator=lambda x: x.startswith("sk-ant-"),
        )
    )

    # Optional checks
    checks.append(
        check_config(
            "OpenAI API Key (for embeddings)",
            getattr(settings, "openai_api_key", None),
            required=False,
            format_hint="sk-xxx (for similarity search)",
        )
    )

    # Display results
    table = Table(title="Configuration Checks")
    table.add_column("Check", style="cyan")
    table.add_column("Status")
    table.add_column("Details", style="dim")

    ok_count = 0
    warn_count = 0
    error_count = 0

    for check in checks:
        status, name, detail = check
        table.add_row(name, status_icon(status), detail if verbose else "")

        if status == CheckStatus.OK:
            ok_count += 1
        elif status == CheckStatus.WARN:
            warn_count += 1
        elif status == CheckStatus.ERROR:
            error_count += 1

    console.print(table)
    rprint()

    # Summary
    if error_count > 0:
        rprint(f"[red]✗ {error_count} required configuration(s) missing or invalid[/red]")
        rprint("[dim]Run with --verbose for details[/dim]")
        raise typer.Exit(1)
    elif warn_count > 0:
        rprint(f"[yellow]⚠ Configuration valid with {warn_count} warning(s)[/yellow]")
    else:
        rprint(f"[green]✓ All {ok_count} configuration checks passed![/green]")


def check_config(
    name: str,
    value: str | None,
    required: bool = True,
    format_hint: str = "",
    validator: Callable | None = None,
) -> tuple[CheckStatus, str, str]:
    """Check a configuration value."""
    if not value:
        if required:
            return (CheckStatus.ERROR, name, f"Missing - {format_hint}")
        return (CheckStatus.SKIP, name, "Optional, not configured")

    if validator and not validator(value):
        return (CheckStatus.WARN, name, f"Format may be invalid - {format_hint}")

    # Mask the value for display
    masked = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "****"
    return (CheckStatus.OK, name, f"Configured ({masked})")


@app.command()
def test_integration(
    integration: str = typer.Argument(
        ..., help="Integration to test: github, datadog, cloudwatch, slack, pagerduty"
    ),
    timeout: int = typer.Option(30, "--timeout", "-t", help="Timeout in seconds"),
):
    """
    Test connectivity to a specific integration.

    Performs a live API call to verify credentials and connectivity.
    """
    from ..config import get_settings

    settings = get_settings()

    rprint(f"[bold]Testing {integration} integration...[/bold]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Connecting to {integration}...", total=None)

        try:
            result = asyncio.run(_test_integration(integration, settings, timeout))
            progress.update(task, completed=True)

            if result["success"]:
                rprint(f"[green]✓ {integration} integration working![/green]")
                for key, value in result.get("details", {}).items():
                    rprint(f"  {key}: {value}")
            else:
                rprint(f"[red]✗ {integration} integration failed[/red]")
                rprint(f"  Error: {result.get('error', 'Unknown error')}")
                raise typer.Exit(1)

        except TimeoutError:
            rprint(f"[red]✗ Timeout after {timeout}s[/red]")
            raise typer.Exit(1)
        except Exception as e:
            rprint(f"[red]✗ Error: {e}[/red]")
            raise typer.Exit(1)


async def _test_integration(integration: str, settings, timeout: int) -> dict:
    """Test a specific integration."""
    integration = integration.lower()

    if integration == "github":
        return await _test_github(settings)
    elif integration == "datadog":
        return await _test_datadog(settings)
    elif integration == "cloudwatch":
        return await _test_cloudwatch(settings)
    elif integration == "slack":
        return await _test_slack(settings)
    elif integration == "pagerduty":
        return await _test_pagerduty(settings)
    else:
        return {"success": False, "error": f"Unknown integration: {integration}"}


async def _test_github(settings) -> dict:
    """Test GitHub API connectivity."""
    import httpx

    if not settings.github_token:
        return {"success": False, "error": "GitHub token not configured"}

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"token {settings.github_token}",
                "Accept": "application/vnd.github.v3+json",
            },
        )

        if response.status_code == 200:
            data = response.json()
            return {
                "success": True,
                "details": {
                    "Authenticated as": data.get("login"),
                    "Rate limit remaining": response.headers.get("x-ratelimit-remaining"),
                },
            }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text[:100]}",
            }


async def _test_datadog(settings) -> dict:
    """Test Datadog API connectivity."""
    import httpx

    if not settings.datadog_api_key or not settings.datadog_app_key:
        return {"success": False, "error": "Datadog API/App keys not configured"}

    site = getattr(settings, "datadog_site", "datadoghq.com")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.{site}/api/v1/validate",
            headers={
                "DD-API-KEY": settings.datadog_api_key,
                "DD-APPLICATION-KEY": settings.datadog_app_key,
            },
        )

        if response.status_code == 200:
            return {
                "success": True,
                "details": {
                    "Site": site,
                    "API Key valid": "Yes",
                },
            }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text[:100]}",
            }


async def _test_cloudwatch(settings) -> dict:
    """Test AWS CloudWatch connectivity."""
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        return {"success": False, "error": "boto3 not installed"}

    region = getattr(settings, "aws_region", "us-east-1")

    try:
        client = boto3.client("logs", region_name=region)
        response = client.describe_log_groups(limit=1)

        return {
            "success": True,
            "details": {
                "Region": region,
                "Log groups accessible": "Yes",
                "Sample group": response.get("logGroups", [{}])[0].get("logGroupName", "N/A"),
            },
        }
    except ClientError as e:
        return {"success": False, "error": str(e)}


async def _test_slack(settings) -> dict:
    """Test Slack API connectivity."""
    import httpx

    if not settings.slack_bot_token:
        return {"success": False, "error": "Slack bot token not configured"}

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://slack.com/api/auth.test",
            headers={"Authorization": f"Bearer {settings.slack_bot_token}"},
        )

        data = response.json()
        if data.get("ok"):
            return {
                "success": True,
                "details": {
                    "Bot user": data.get("user"),
                    "Team": data.get("team"),
                    "Default channel": settings.slack_default_channel,
                },
            }
        else:
            return {"success": False, "error": data.get("error", "Unknown error")}


async def _test_pagerduty(settings) -> dict:
    """Test PagerDuty API connectivity."""
    import httpx

    if not settings.pagerduty_api_key:
        return {"success": False, "error": "PagerDuty API key not configured"}

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.pagerduty.com/abilities",
            headers={
                "Authorization": f"Token token={settings.pagerduty_api_key}",
                "Accept": "application/vnd.pagerduty+json;version=2",
            },
        )

        if response.status_code == 200:
            data = response.json()
            return {
                "success": True,
                "details": {
                    "Abilities": len(data.get("abilities", [])),
                    "Webhooks enabled": "webhooks" in data.get("abilities", []),
                },
            }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text[:100]}",
            }


@app.command()
def test_all(
    timeout: int = typer.Option(30, "--timeout", "-t", help="Timeout per integration"),
):
    """
    Test all configured integrations.

    Runs connectivity tests for all integrations that are configured.
    """
    from ..config import get_settings

    settings = get_settings()

    rprint(Panel.fit("[bold blue]Testing All Integrations[/bold blue]"))
    rprint()

    integrations = ["github", "slack"]

    # Add log provider
    log_provider = getattr(settings, "log_provider", "datadog")
    integrations.append(log_provider)

    # Optional integrations
    if settings.pagerduty_api_key:
        integrations.append("pagerduty")

    results = []

    for integration in integrations:
        rprint(f"Testing {integration}...", end=" ")
        try:
            result = asyncio.run(_test_integration(integration, settings, timeout))
            if result["success"]:
                rprint("[green]✓[/green]")
                results.append((integration, True, None))
            else:
                rprint(f"[red]✗[/red] {result.get('error', '')}")
                results.append((integration, False, result.get("error")))
        except Exception as e:
            rprint(f"[red]✗[/red] {e}")
            results.append((integration, False, str(e)))

    rprint()

    passed = sum(1 for _, success, _ in results if success)
    total = len(results)

    if passed == total:
        rprint(f"[green]✓ All {total} integrations working![/green]")
    else:
        rprint(f"[yellow]⚠ {passed}/{total} integrations working[/yellow]")
        raise typer.Exit(1)


@app.command()
def send_test(
    channel: str | None = typer.Option(None, "--channel", "-c", help="Slack channel to send to"),
    scenario: str = typer.Option(
        "demo-stripe-timeout", "--scenario", "-s", help="Demo scenario to use"
    ),
):
    """
    Send a test context card to Slack.

    Generates a demo context card and posts it to the specified Slack channel.
    """
    from ..config import get_settings
    from ..demo import DemoGenerator

    settings = get_settings()
    target_channel = channel or settings.slack_default_channel

    rprint(f"[bold]Sending test context card to {target_channel}...[/bold]")

    async def send():
        from ..delivery.slack import SlackDelivery

        generator = DemoGenerator(simulate_delays=False)
        card = await generator.generate_context_card(scenario)

        slack = SlackDelivery(settings)
        result = await slack.deliver(card, channel=target_channel)
        return result

    try:
        result = asyncio.run(send())
        if result.get("ok"):
            rprint(f"[green]✓ Test card sent to {target_channel}![/green]")
            rprint(f"  Message timestamp: {result.get('ts')}")
        else:
            rprint(f"[red]✗ Failed to send: {result.get('error')}[/red]")
            raise typer.Exit(1)
    except Exception as e:
        rprint(f"[red]✗ Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def version():
    """Show version information."""
    rprint("[bold]Incident Copilot[/bold]")
    rprint("Version: 0.1.0")
    rprint("Python: " + sys.version.split()[0])


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
