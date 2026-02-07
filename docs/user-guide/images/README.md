# Documentation Images

This folder contains images, screenshots, and diagrams for the Incident Copilot user documentation.

## Image Naming Convention

Use descriptive, lowercase names with hyphens:
- `{feature}-{description}.png`
- Example: `slack-context-card.png`, `pagerduty-webhook-setup.png`

## Required Screenshots

The following screenshots should be captured for complete documentation:

### Overview
- [ ] `overview-placeholder.png` - Context card in Slack showing all sections

### Getting Started
- [ ] `docker-compose-placeholder.png` - Docker Compose showing healthy containers
- [ ] `swagger-ui-placeholder.png` - Swagger UI at /docs endpoint
- [ ] `slack-context-card-placeholder.png` - First context card in Slack

### PagerDuty Integration
- [ ] `pagerduty-api-key-placeholder.png` - Creating API key in PagerDuty
- [ ] `pagerduty-webhook-placeholder.png` - Webhook configuration screen

### Opsgenie Integration
- [ ] `opsgenie-api-key-placeholder.png` - API key creation
- [ ] `opsgenie-webhook-placeholder.png` - Webhook setup

### GitHub Integration
- [ ] `github-pat-placeholder.png` - Personal Access Token creation
- [ ] `github-app-placeholder.png` - GitHub App setup

### Slack Integration
- [ ] `slack-app-create-placeholder.png` - Creating Slack app
- [ ] `slack-permissions-placeholder.png` - Bot token scopes
- [ ] `slack-install-placeholder.png` - Installing to workspace

### Context Cards
- [ ] `context-card-full-placeholder.png` - Full context card with all sections
- [ ] `context-card-deployments-placeholder.png` - Deployment section detail
- [ ] `context-card-logs-placeholder.png` - Log analysis section

### Reports
- [ ] `report-daily-placeholder.png` - Daily digest in Slack
- [ ] `report-weekly-placeholder.png` - Weekly report example
- [ ] `report-email-placeholder.png` - HTML email report

### Admin
- [ ] `admin-api-keys-placeholder.png` - API key management UI
- [ ] `admin-sso-placeholder.png` - SSO configuration

## Diagram Guidelines

For architectural diagrams:
- Use Mermaid for simple flowcharts (rendered in GitHub)
- Use ASCII art for terminal-friendly diagrams
- Export Figma/draw.io diagrams as PNG at 2x resolution

## Image Specifications

| Type | Format | Max Width | Notes |
|------|--------|-----------|-------|
| Screenshots | PNG | 1200px | Retina-friendly |
| Diagrams | PNG/SVG | 1000px | SVG preferred |
| Icons | SVG | 64px | Vector format |

## Accessibility

- All images should have descriptive alt text in markdown
- Use high contrast for diagrams
- Avoid relying solely on color to convey information

## Updating Images

When updating screenshots:
1. Capture at 2x resolution on Retina display
2. Crop to relevant area
3. Add subtle shadow/border if needed
4. Compress with `pngquant` or similar
5. Update any changed filenames in documentation

## Placeholder Pattern

Until real screenshots are captured, use placeholder references:
```markdown
![Description](./images/feature-placeholder.png)
*Caption: What this screenshot will show*
```

This allows documentation to be written before all screenshots exist.
