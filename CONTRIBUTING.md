# Contributing to Incident Copilot

Thank you for your interest in contributing! This guide will help you get started.

## Table of Contents

- [Development Setup](#development-setup)
- [Code Style](#code-style)
- [Testing Guidelines](#testing-guidelines)
- [Pull Request Process](#pull-request-process)
- [Commit Messages](#commit-messages)
- [Architecture Guidelines](#architecture-guidelines)

---

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 18+ (for frontend, optional)
- Docker & Docker Compose
- Git

### Quick Start

```bash
# Clone the repository
git clone https://github.com/jianxux/incident-copilot.git
cd incident-copilot

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or `.venv\Scripts\activate` on Windows

# Install dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pip install pre-commit
pre-commit install

# Copy environment template
cp .env.example .env
# Edit .env with your API keys

# Run the development server
make dev
# or: uvicorn src.main:app --reload
```

### Using Make Commands

```bash
make help          # Show all available commands
make dev           # Start development server
make test          # Run all tests
make test-fast     # Run unit tests only (faster)
make lint          # Run linters
make format        # Auto-format code
make check         # lint + typecheck + test
make coverage      # Generate coverage report
```

### Docker Development

```bash
# Build and run with Docker Compose
docker-compose up --build

# Run tests in container
docker-compose run --rm app pytest
```

---

## Code Style

We use automated formatters and linters to maintain consistent code style.

### Tools

| Tool | Purpose | Config |
|------|---------|--------|
| **Black** | Code formatting | `pyproject.toml` |
| **isort** | Import sorting | `pyproject.toml` |
| **Ruff** | Fast linting | `pyproject.toml` |
| **mypy** | Type checking | `pyproject.toml` |

### Pre-commit Hooks

Pre-commit hooks run automatically on every commit:

```bash
# Install hooks (one-time)
pre-commit install

# Run manually on all files
pre-commit run --all-files

# Skip hooks (not recommended)
git commit --no-verify
```

### Style Guidelines

```python
# ✓ Good: Use type hints
def process_incident(incident_id: str, service: str) -> ContextCard:
    ...

# ✓ Good: Use dataclasses or Pydantic for data structures
@dataclass
class LogEntry:
    timestamp: datetime
    level: LogLevel
    message: str

# ✓ Good: Async for I/O operations
async def fetch_logs(service: str) -> list[LogEntry]:
    ...

# ✓ Good: Use StrEnum for string enums (Python 3.11+)
class LogLevel(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

# ✗ Bad: Don't use (str, Enum) pattern
class LogLevel(str, Enum):  # Use StrEnum instead
    ...
```

### Import Order

Imports are sorted by isort into groups:

```python
# 1. Standard library
import asyncio
from datetime import datetime

# 2. Third-party packages
import httpx
from pydantic import BaseModel

# 3. Local imports
from src.models import ContextCard
from src.config import Settings
```

---

## Testing Guidelines

### Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── integration/             # Integration tests
│   └── test_webhooks.py
├── test_analytics.py        # Unit tests
├── test_log_compressor.py
└── ...
```

### Running Tests

```bash
# All tests
make test
# or: pytest

# With coverage
make coverage
# or: pytest --cov=src --cov-report=html

# Specific file
pytest tests/test_log_compressor.py

# Specific test
pytest tests/test_log_compressor.py::TestLogParser::test_parse_error

# Fast tests only (skip slow/integration)
make test-fast
# or: pytest -m "not slow and not integration"
```

### Writing Tests

```python
import pytest
from src.ai.log_compressor import LogCompressor, LogEntry

class TestLogCompressor:
    """Tests for LogCompressor class."""

    def test_compress_empty_logs(self):
        """Empty input should return empty output."""
        compressor = LogCompressor()
        result = compressor.compress([])
        assert result.entries == []
        assert result.summary == ""

    def test_compress_deduplicates(self):
        """Duplicate log messages should be grouped."""
        entries = [
            LogEntry(message="Connection timeout"),
            LogEntry(message="Connection timeout"),
            LogEntry(message="Connection timeout"),
        ]
        compressor = LogCompressor()
        result = compressor.compress(entries)
        
        assert len(result.patterns) == 1
        assert result.patterns[0].count == 3

    @pytest.mark.asyncio
    async def test_compress_with_llm(self, mock_anthropic):
        """LLM summarization should be called for large inputs."""
        # ... async test
```

### Test Markers

```python
@pytest.mark.slow           # Slow tests (>1s)
@pytest.mark.integration    # Requires external services
@pytest.mark.asyncio        # Async tests
```

### Fixtures

Common fixtures are in `tests/conftest.py`:

```python
@pytest.fixture
def sample_incident():
    """Create a sample incident for testing."""
    return Incident(
        id="INC-123",
        service="payment-api",
        severity="high",
    )

@pytest.fixture
def mock_anthropic(mocker):
    """Mock Anthropic API client."""
    return mocker.patch("src.ai.summarizer.AsyncAnthropic")
```

---

## Pull Request Process

### Before Submitting

1. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/my-feature
   # or: git checkout -b fix/bug-description
   ```

2. **Make your changes** with clear, focused commits

3. **Run the full check suite**:
   ```bash
   make check  # lint + typecheck + test
   ```

4. **Update documentation** if needed

5. **Add tests** for new functionality

### PR Requirements

- [ ] All CI checks pass (lint, typecheck, test, security)
- [ ] Tests added for new functionality
- [ ] Documentation updated if needed
- [ ] No decrease in test coverage
- [ ] Follows module dependency rules (see [Architecture](docs/architecture.md))

### PR Template

```markdown
## Description
Brief description of changes.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
Describe how you tested the changes.

## Checklist
- [ ] I have run `make check` locally
- [ ] I have added tests for my changes
- [ ] I have updated documentation as needed
```

### Review Process

1. Open PR against `main`
2. CI runs automatically
3. Request review from maintainers
4. Address feedback
5. Squash and merge when approved

---

## Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Types

| Type | Description |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Formatting, no code change |
| `refactor` | Code change that neither fixes nor adds |
| `test` | Adding or updating tests |
| `chore` | Build process, dependencies |
| `perf` | Performance improvement |

### Examples

```bash
# Feature
git commit -m "feat(ai): add log compression pipeline"

# Bug fix
git commit -m "fix(pagerduty): handle missing incident fields"

# Documentation
git commit -m "docs: update architecture diagram"

# Breaking change
git commit -m "feat(api)!: change webhook payload format

BREAKING CHANGE: webhook payload now uses snake_case"
```

---

## Architecture Guidelines

### Module Dependencies

See [docs/architecture.md](docs/architecture.md) for the full dependency matrix.

**Key rules:**
- `models.py` has no dependencies (except stdlib)
- `integrations/` cannot import from `orchestrator` (circular!)
- `ai/` cannot import from `integrations/` (coupling!)
- Only `orchestrator.py` and `api/` can import integrations

### Adding New Integrations

1. Create adapter in `src/integrations/`:
   ```python
   # src/integrations/newservice.py
   from src.models import Context
   from src.config import Settings

   class NewServiceAdapter:
       async def get_context(self, service: str) -> Context:
           ...
       
       async def health_check(self) -> bool:
           ...
   ```

2. Add configuration to `src/config.py`

3. Wire up in `src/orchestrator.py`

4. Add tests in `tests/test_newservice.py`

### Adding New AI Features

1. Add to `src/ai/`
2. Use Haiku for high-volume/cost-sensitive (log compression)
3. Use Sonnet for quality-critical (analysis, chat)
4. Add eval cases to `src/eval/synthetic.py`

---

## Getting Help

- **Questions**: Open a [Discussion](https://github.com/jianxux/incident-copilot/discussions)
- **Bugs**: Open an [Issue](https://github.com/jianxux/incident-copilot/issues)
- **Security**: Email security@example.com (do not open public issue)

---

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.
