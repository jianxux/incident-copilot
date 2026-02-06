# Screenshots and Images

This directory contains screenshots and images for the user documentation.

## Required Screenshots

The following screenshots should be added to complete the documentation:

### Getting Started
- `overview-placeholder.png` - Example context card in Slack
- `docker-compose-placeholder.png` - Docker Compose showing healthy containers
- `swagger-ui-placeholder.png` - Interactive API documentation at /docs

### PagerDuty Integration
- `pagerduty-api-key-placeholder.png` - Creating a PagerDuty API key
- `pagerduty-webhook-placeholder.png` - Configuring PagerDuty webhook

### Slack Integration
- `slack-create-app-placeholder.png` - Creating a new Slack app
- `slack-scopes-placeholder.png` - Adding Slack bot scopes
- `slack-context-card-placeholder.png` - Context card in Slack channel

### GitHub Integration
- `github-pat-placeholder.png` - Creating GitHub personal access token

### Teams Integration
- `teams-webhook-placeholder.png` - Creating Teams incoming webhook

## Screenshot Guidelines

When adding screenshots:

1. **Size**: 800-1200px width, maintain aspect ratio
2. **Format**: PNG for UI screenshots, SVG for diagrams
3. **Annotations**: Use red arrows/boxes for emphasis
4. **Privacy**: Blur or redact sensitive information
5. **Naming**: Use descriptive kebab-case names

## Creating Placeholders

For documentation review, you can use placeholder images:

```bash
# Generate a placeholder image (requires ImageMagick)
convert -size 800x400 xc:lightgray \
  -gravity center \
  -pointsize 24 \
  -annotate 0 "Screenshot: Context Card in Slack" \
  slack-context-card-placeholder.png
```

Or use online placeholder services during development:
```markdown
![Placeholder](https://via.placeholder.com/800x400?text=Context+Card+in+Slack)
```
