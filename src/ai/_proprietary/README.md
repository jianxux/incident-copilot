# Proprietary AI Engine

This directory contains the proprietary AI logic — prompts, chains, and analysis pipelines.

In the open-source version, these are replaced by the AI service client (`../client.py`) 
which calls a remote AI service, or falls back to stub responses.

**For self-hosted deployments:** Keep this directory to use the built-in AI engine directly.

**For the hosted SaaS version:** This code runs as a separate private service.
Set `AI_SERVICE_URL` in your environment to point to the AI service endpoint.
