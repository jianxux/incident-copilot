# Changelog

All notable changes to Incident Copilot will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Web dashboard for viewing incidents and context cards
- Past incident similarity search using vector embeddings
- Opsgenie integration for alert ingestion
- AWS CloudWatch integration for log fetching
- Automatic runbook linking based on alert context
- CI/CD workflows for GitHub Actions
- Contributing guidelines
- Architecture documentation
- Demo script for product presentations
- Marketing landing page

### Changed
- Orchestrator now supports multiple log providers (Datadog, CloudWatch)
- Configuration supports provider selection via environment variables

## [0.1.0] - 2026-01-27

### Added
- Initial MVP release
- PagerDuty webhook integration
- GitHub deployment fetching
- Datadog log fetching
- AI-powered log summarization using Claude
- Slack context card delivery
- Docker and Docker Compose support
- FastAPI-based API server
- Pydantic models for type safety
- Structured logging with structlog
- Basic test suite

### Documentation
- README with quick start guide
- API endpoint documentation
- Configuration reference
- Project structure overview

---

## Versioning

- **0.x.y**: Pre-production development
- **1.0.0**: First production-ready release (planned)
- **Major**: Breaking API or config changes
- **Minor**: New features, backwards compatible
- **Patch**: Bug fixes, backwards compatible
