# Contributing to Incident Copilot

## Development Setup

```bash
# Clone and install
git clone https://github.com/jianxux/incident-copilot.git
cd incident-copilot
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run tests
make test

# Run linting
make lint
```

## Code Quality Standards

### Every PR Must Have:

1. **Unit Tests** - Minimum 80% coverage for new code
2. **Type Hints** - All public functions typed
3. **Documentation** - Docstrings for public APIs
4. **Passing CI** - All checks green (lint, type, test)

### Before Committing:

```bash
# Format code
make format

# Run all checks
make check

# Run tests
make test
```

## Testing Guidelines

### Test Structure

```
tests/
├── test_<module>.py          # Unit tests for src/<module>
├── integration/              # Integration tests (require services)
│   ├── test_api.py
│   └── test_webhooks.py
└── e2e/                      # End-to-end tests
    └── test_full_flow.py
```

### Writing Tests

```python
# Good: Descriptive names, single assertion per test
def test_log_parser_extracts_error_level_from_iso_format():
    parser = LogParser()
    entry = parser.parse("2024-01-15T10:30:45Z [ERROR] [api] Failed")
    assert entry.level == LogLevel.ERROR

# Good: Test edge cases
def test_log_parser_returns_none_for_empty_string():
    parser = LogParser()
    assert parser.parse("") is None

# Good: Integration test with fixtures
@pytest.fixture
def mock_datadog():
    with responses.RequestsMock() as rsps:
        rsps.add(...)
        yield rsps

async def test_datadog_adapter_fetches_logs(mock_datadog):
    adapter = DatadogAdapter(settings)
    logs = await adapter.get_logs("api", minutes=30)
    assert len(logs) > 0
```

## Architecture Guidelines

### Module Dependencies

```
ALLOWED:
  api/           → orchestrator, models
  orchestrator   → ai/, integrations/, dependencies/
  ai/            → models, config
  integrations/  → models, config
  dependencies/  → models
  eval/          → ai/, models

FORBIDDEN:
  integrations/ → orchestrator (circular)
  ai/ → integrations/ (coupling)
```

### Adding a New Integration

1. Create `src/integrations/<name>.py`
2. Implement the appropriate adapter interface
3. Add configuration to `src/config.py`
4. Write unit tests in `tests/test_<name>.py`
5. Update `docs/integration-guide.md`

### Adding a New Feature

1. Write ADR in `docs/adr/` if architectural
2. Create feature branch: `git checkout -b feature/my-feature`
3. Implement with tests
4. Update documentation
5. Open PR with description

## Pull Request Process

1. **Branch naming**: `feature/`, `fix/`, `docs/`, `refactor/`
2. **Commit messages**: Use conventional commits
   - `feat: Add log compression pipeline`
   - `fix: Handle empty log lines`
   - `test: Add rubric scoring tests`
   - `docs: Update architecture diagram`
3. **PR description**: Explain what and why
4. **Tests**: Must pass, coverage must not decrease
5. **Review**: At least one approval required

## Code Style

- **Formatter**: Black (line length 100)
- **Linter**: Ruff
- **Type checker**: mypy
- **Imports**: isort (black profile)

```python
# Good: Type hints + docstring
async def get_blast_radius(
    service_id: str,
    max_depth: int = 3,
) -> BlastRadius:
    """
    Calculate blast radius for a service.
    
    Args:
        service_id: The service to analyze
        max_depth: How many levels of dependencies to traverse
        
    Returns:
        BlastRadius with affected services and critical paths
    """
    ...
```

## Release Process

1. Update `CHANGELOG.md`
2. Bump version in `pyproject.toml`
3. Create release PR
4. After merge, tag: `git tag v0.1.0`
5. CI builds and pushes Docker image
