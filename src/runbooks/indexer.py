"""
Runbook indexer - fetches and indexes runbooks from configured sources.

Supports:
- GitHub repositories (markdown files)
- Notion pages (via API)
- Confluence (via URL patterns)
- Local directories

Run with: python -m src.runbooks.indexer --reindex
"""

import asyncio
import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx
import structlog

from ..config import Settings, get_settings
from .models import Runbook, RunbookIndex, RunbookSource, RunbookSourceType

logger = structlog.get_logger()

# Default index storage path
INDEX_PATH = Path("data/runbook_index.json")


class RunbookIndexer:
    """Indexes runbooks from multiple sources."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._index: RunbookIndex | None = None

    @property
    def index_path(self) -> Path:
        """Get the index file path."""
        return INDEX_PATH

    async def reindex(self, sources: list[RunbookSource] | None = None) -> RunbookIndex:
        """
        Reindex all runbooks from configured sources.

        Args:
            sources: Optional list of sources to index. Uses config if not provided.

        Returns:
            The built runbook index.
        """
        if sources is None:
            sources = self._get_configured_sources()

        logger.info("runbook_reindex_starting", source_count=len(sources))

        all_runbooks: list[Runbook] = []
        vocabulary: Counter[str] = Counter()

        for source in sources:
            if not source.enabled:
                logger.debug("runbook_source_disabled", source=source.name)
                continue

            try:
                runbooks = await self._fetch_source(source)
                logger.info(
                    "runbook_source_indexed",
                    source=source.name,
                    type=source.type.value,
                    runbook_count=len(runbooks),
                )
                all_runbooks.extend(runbooks)

                # Update vocabulary
                for rb in runbooks:
                    vocabulary.update(rb.keywords)

            except Exception as e:
                logger.error(
                    "runbook_source_failed",
                    source=source.name,
                    error=str(e),
                )

        # Build index
        self._index = RunbookIndex(
            version="1.0",
            built_at=datetime.now(UTC),
            runbooks=all_runbooks,
            vocabulary=dict(vocabulary),
        )

        # Save to disk
        self._save_index()

        logger.info(
            "runbook_reindex_complete",
            total_runbooks=len(all_runbooks),
            vocabulary_size=len(vocabulary),
        )

        return self._index

    def load_index(self) -> RunbookIndex | None:
        """Load index from disk."""
        if self._index is not None:
            return self._index

        if not self.index_path.exists():
            logger.warning("runbook_index_not_found", path=str(self.index_path))
            return None

        try:
            with open(self.index_path) as f:
                data = json.load(f)
            self._index = RunbookIndex.model_validate(data)
            logger.info(
                "runbook_index_loaded",
                runbook_count=len(self._index.runbooks),
                built_at=self._index.built_at.isoformat(),
            )
            return self._index
        except Exception as e:
            logger.error("runbook_index_load_failed", error=str(e))
            return None

    def _save_index(self) -> None:
        """Save index to disk."""
        if self._index is None:
            return

        self.index_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.index_path, "w") as f:
            json.dump(self._index.model_dump(mode="json"), f, indent=2, default=str)

        logger.debug("runbook_index_saved", path=str(self.index_path))

    def _get_configured_sources(self) -> list[RunbookSource]:
        """Get runbook sources from settings."""
        # Check for RUNBOOK_SOURCES in settings
        sources_config = getattr(self.settings, "runbook_sources", [])

        if not sources_config:
            logger.warning("no_runbook_sources_configured")
            return []

        sources = []
        for cfg in sources_config:
            try:
                if isinstance(cfg, dict):
                    sources.append(RunbookSource.model_validate(cfg))
                elif isinstance(cfg, RunbookSource):
                    sources.append(cfg)
            except Exception as e:
                logger.error("invalid_runbook_source_config", config=cfg, error=str(e))

        return sources

    async def _fetch_source(self, source: RunbookSource) -> list[Runbook]:
        """Fetch runbooks from a source based on its type."""
        match source.type:
            case RunbookSourceType.GITHUB:
                return await self._fetch_github(source)
            case RunbookSourceType.NOTION:
                return await self._fetch_notion(source)
            case RunbookSourceType.CONFLUENCE:
                return await self._fetch_confluence(source)
            case RunbookSourceType.LOCAL:
                return await self._fetch_local(source)
            case _:
                logger.warning("unknown_source_type", type=source.type)
                return []

    async def _fetch_github(self, source: RunbookSource) -> list[Runbook]:
        """Fetch markdown runbooks from a GitHub repository."""
        if not source.repo:
            raise ValueError("GitHub source requires 'repo' field")

        runbooks = []
        async with httpx.AsyncClient() as client:
            headers = {}
            if self.settings.github_token:
                headers["Authorization"] = f"Bearer {self.settings.github_token}"
                headers["Accept"] = "application/vnd.github.v3+json"

            for path in source.paths:
                # Get directory contents
                api_url = f"https://api.github.com/repos/{source.repo}/contents/{path}"
                params = {"ref": source.branch}

                try:
                    resp = await client.get(api_url, headers=headers, params=params)
                    if resp.status_code == 404:
                        logger.warning(
                            "github_path_not_found",
                            repo=source.repo,
                            path=path,
                        )
                        continue

                    resp.raise_for_status()
                    files = resp.json()

                    # Fetch each markdown file
                    for file_info in files:
                        if not file_info["name"].endswith(".md"):
                            continue

                        # Get file content
                        content_resp = await client.get(
                            file_info["download_url"], headers=headers
                        )
                        content_resp.raise_for_status()
                        content = content_resp.text

                        # Parse and create runbook
                        runbook = self._parse_markdown_runbook(
                            content=content,
                            filename=file_info["name"],
                            url=file_info["html_url"],
                            source=source,
                        )
                        runbooks.append(runbook)

                except httpx.HTTPError as e:
                    logger.error(
                        "github_fetch_error",
                        repo=source.repo,
                        path=path,
                        error=str(e),
                    )

        return runbooks

    async def _fetch_notion(self, source: RunbookSource) -> list[Runbook]:
        """Fetch runbooks from Notion database."""
        if not source.notion_token or not source.notion_database_id:
            raise ValueError(
                "Notion source requires 'notion_token' and 'notion_database_id'"
            )

        runbooks = []
        async with httpx.AsyncClient() as client:
            headers = {
                "Authorization": f"Bearer {source.notion_token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            }

            # Query database
            db_url = (
                f"https://api.notion.com/v1/databases/{source.notion_database_id}/query"
            )

            try:
                resp = await client.post(db_url, headers=headers, json={})
                resp.raise_for_status()
                results = resp.json()

                for page in results.get("results", []):
                    # Extract title from properties
                    title = "Untitled"
                    for prop_name, prop_value in page.get("properties", {}).items():
                        if prop_value.get("type") == "title":
                            title_parts = prop_value.get("title", [])
                            if title_parts:
                                title = title_parts[0].get("plain_text", "Untitled")
                            break

                    # Get page content
                    page_id = page["id"]
                    blocks_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
                    blocks_resp = await client.get(blocks_url, headers=headers)
                    blocks_resp.raise_for_status()
                    blocks = blocks_resp.json()

                    # Extract text content from blocks
                    content_parts = []
                    for block in blocks.get("results", []):
                        block_type = block.get("type", "")
                        if block_type in (
                            "paragraph",
                            "heading_1",
                            "heading_2",
                            "heading_3",
                            "bulleted_list_item",
                        ):
                            rich_text = block.get(block_type, {}).get("rich_text", [])
                            for text_obj in rich_text:
                                content_parts.append(text_obj.get("plain_text", ""))

                    content = "\n".join(content_parts)

                    # Create runbook
                    runbook_id = f"notion-{page_id}"
                    url = page.get(
                        "url", f"https://notion.so/{page_id.replace('-', '')}"
                    )

                    runbook = Runbook(
                        id=runbook_id,
                        title=title,
                        url=url,
                        source_type=RunbookSourceType.NOTION,
                        source_name=source.name,
                        content=content,
                        keywords=self._extract_keywords(f"{title} {content}"),
                        tags=self._extract_tags(content),
                        services=self._extract_services(content),
                        content_hash=hashlib.md5(
                            content.encode(), usedforsecurity=False
                        ).hexdigest(),
                    )
                    runbooks.append(runbook)

            except httpx.HTTPError as e:
                logger.error("notion_fetch_error", error=str(e))

        return runbooks

    async def _fetch_confluence(self, source: RunbookSource) -> list[Runbook]:
        """
        Fetch runbooks from Confluence.

        Note: Basic implementation using REST API. Requires API token auth.
        """
        if not source.confluence_url or not source.confluence_space:
            raise ValueError(
                "Confluence source requires 'confluence_url' and 'confluence_space'"
            )

        runbooks = []

        # Extract credentials from URL or environment
        # Expected format: https://user:token@company.atlassian.net/wiki
        base_url = source.confluence_url.rstrip("/")

        async with httpx.AsyncClient() as client:
            # Search for pages in space with "runbook" label or in runbooks folder
            search_url = f"{base_url}/rest/api/content"
            params = {
                "spaceKey": source.confluence_space,
                "type": "page",
                "expand": "body.storage,metadata.labels",
                "limit": 100,
            }

            try:
                resp = await client.get(search_url, params=params)
                resp.raise_for_status()
                results = resp.json()

                for page in results.get("results", []):
                    # Check if page has runbook-related labels
                    labels = [
                        lbl["name"]
                        for lbl in page.get("metadata", {})
                        .get("labels", {})
                        .get("results", [])
                    ]

                    # Filter for runbook-related pages
                    is_runbook = (
                        any(
                            lbl
                            in [
                                "runbook",
                                "runbooks",
                                "operations",
                                "oncall",
                                "incident",
                            ]
                            for lbl in labels
                        )
                        or "runbook" in page.get("title", "").lower()
                    )

                    if not is_runbook:
                        continue

                    # Parse HTML content to plain text
                    html_content = (
                        page.get("body", {}).get("storage", {}).get("value", "")
                    )
                    content = self._html_to_text(html_content)

                    page_url = f"{base_url}{page['_links']['webui']}"

                    runbook = Runbook(
                        id=f"confluence-{page['id']}",
                        title=page["title"],
                        url=page_url,
                        source_type=RunbookSourceType.CONFLUENCE,
                        source_name=source.name,
                        content=content,
                        keywords=self._extract_keywords(f"{page['title']} {content}"),
                        tags=labels,
                        services=self._extract_services(content),
                        content_hash=hashlib.md5(
                            content.encode(), usedforsecurity=False
                        ).hexdigest(),
                    )
                    runbooks.append(runbook)

            except httpx.HTTPError as e:
                logger.error("confluence_fetch_error", error=str(e))

        return runbooks

    async def _fetch_local(self, source: RunbookSource) -> list[Runbook]:
        """Fetch runbooks from a local directory."""
        if not source.local_path:
            raise ValueError("Local source requires 'local_path' field")

        local_dir = Path(source.local_path)
        if not local_dir.exists():
            logger.warning("local_runbook_path_not_found", path=source.local_path)
            return []

        runbooks = []
        for md_file in local_dir.rglob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")

                # Build URL
                rel_path = md_file.relative_to(local_dir)
                if source.base_url:
                    url = f"{source.base_url.rstrip('/')}/{rel_path}"
                else:
                    url = f"file://{md_file.absolute()}"

                runbook = self._parse_markdown_runbook(
                    content=content,
                    filename=md_file.name,
                    url=url,
                    source=source,
                )
                runbooks.append(runbook)

            except Exception as e:
                logger.error(
                    "local_file_read_error",
                    file=str(md_file),
                    error=str(e),
                )

        return runbooks

    def _parse_markdown_runbook(
        self,
        content: str,
        filename: str,
        url: str,
        source: RunbookSource,
    ) -> Runbook:
        """Parse a markdown file into a Runbook object."""
        # Extract title from first heading or filename
        title = filename.replace(".md", "").replace("-", " ").replace("_", " ").title()
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()

        # Extract description from first paragraph
        description = None
        desc_match = re.search(r"^#.*\n\n(.+?)(?:\n\n|$)", content, re.DOTALL)
        if desc_match:
            description = desc_match.group(1).strip()[:200]

        # Generate unique ID
        runbook_id = f"{source.type.value}-{hashlib.md5(url.encode(), usedforsecurity=False).hexdigest()[:12]}"

        return Runbook(
            id=runbook_id,
            title=title,
            url=url,
            source_type=source.type,
            source_name=source.name,
            content=content,
            description=description,
            keywords=self._extract_keywords(f"{title} {content}"),
            tags=self._extract_tags(content),
            services=self._extract_services(content),
            content_hash=hashlib.md5(
                content.encode(), usedforsecurity=False
            ).hexdigest(),
        )

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract keywords from text using simple tokenization and filtering."""
        # Common stopwords
        stopwords = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "as",
            "is",
            "was",
            "are",
            "were",
            "been",
            "be",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "can",
            "this",
            "that",
            "these",
            "those",
            "it",
            "its",
            "they",
            "them",
            "their",
            "we",
            "you",
            "your",
            "he",
            "she",
            "him",
            "her",
            "his",
            "hers",
            "if",
            "then",
            "else",
            "when",
            "where",
            "what",
            "which",
            "who",
            "how",
            "why",
            "all",
            "any",
            "both",
            "each",
            "more",
            "most",
            "other",
            "some",
            "such",
            "no",
            "not",
            "only",
            "same",
            "so",
            "than",
            "too",
            "very",
            "just",
            "also",
            "now",
        }

        # Tokenize: extract words, lowercase, filter
        words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b", text.lower())

        # Count and filter
        word_counts = Counter(words)
        keywords = [
            word
            for word, count in word_counts.most_common(50)
            if word not in stopwords and count >= 1
        ]

        return keywords[:30]  # Return top 30 keywords

    def _extract_tags(self, content: str) -> list[str]:
        """Extract tags from markdown frontmatter or inline tags."""
        tags = []

        # YAML frontmatter tags
        frontmatter_match = re.search(r"^---\n(.+?)\n---", content, re.DOTALL)
        if frontmatter_match:
            fm_content = frontmatter_match.group(1)
            tags_match = re.search(r"tags:\s*\[(.+?)\]", fm_content)
            if tags_match:
                tags.extend(
                    [t.strip().strip("'\"") for t in tags_match.group(1).split(",")]
                )
            # Also try YAML list format
            tags_list = re.findall(r"tags:\s*\n((?:\s*-\s*.+\n?)+)", fm_content)
            for tag_block in tags_list:
                tags.extend(re.findall(r"-\s*(.+)", tag_block))

        # Inline hashtags
        hashtags = re.findall(r"#([a-zA-Z][a-zA-Z0-9_-]+)", content)
        tags.extend(hashtags)

        return list(set(tags))[:20]

    def _extract_services(self, content: str) -> list[str]:
        """Extract service names from content."""
        services = []

        # Look for common patterns
        patterns = [
            r"service:\s*([a-zA-Z0-9_-]+)",
            r"services?:\s*\[(.+?)\]",
            r"@service\s+([a-zA-Z0-9_-]+)",
            r"## Service:\s*(.+)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                if "," in match:
                    services.extend([s.strip().strip("'\"") for s in match.split(",")])
                else:
                    services.append(match.strip())

        return list(set(services))

    def _html_to_text(self, html: str) -> str:
        """Convert HTML to plain text (simple implementation)."""
        # Remove tags
        text = re.sub(r"<[^>]+>", " ", html)
        # Decode entities
        text = text.replace("&nbsp;", " ").replace("&amp;", "&")
        text = text.replace("&lt;", "<").replace("&gt;", ">")
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text


# CLI entry point
async def main():
    """CLI entry point for runbook indexer."""
    import argparse

    parser = argparse.ArgumentParser(description="Runbook Indexer")
    parser.add_argument("--reindex", action="store_true", help="Reindex all runbooks")
    parser.add_argument("--source", type=str, help="Index only specific source by name")
    parser.add_argument("--stats", action="store_true", help="Show index statistics")
    args = parser.parse_args()

    indexer = RunbookIndexer()

    if args.stats:
        index = indexer.load_index()
        if index:
            print("Runbook Index Statistics")
            print("========================")
            print(f"Built at: {index.built_at}")
            print(f"Total runbooks: {len(index.runbooks)}")
            print(f"Vocabulary size: {len(index.vocabulary)}")
            print()
            by_source = {}
            for rb in index.runbooks:
                key = f"{rb.source_type.value}:{rb.source_name}"
                by_source[key] = by_source.get(key, 0) + 1
            print("By source:")
            for src, count in sorted(by_source.items()):
                print(f"  {src}: {count}")
        else:
            print("No index found. Run with --reindex first.")
        return

    if args.reindex:
        print("Reindexing runbooks...")
        index = await indexer.reindex()
        print(f"Indexed {len(index.runbooks)} runbooks")
        print(f"Vocabulary size: {len(index.vocabulary)}")
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
