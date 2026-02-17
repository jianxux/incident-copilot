# Contributing

Contributions are welcome.

## Development setup

### Prerequisites

- Python 3.11
- Docker (for Postgres/Redis)

### Install

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

### Run backing services

```bash
docker compose up -d postgres redis
```

### Configure env

```bash
cp .env.example .env 2>/dev/null || true
```

Set at least `DATABASE_URL`, `REDIS_URL`, and `SECRET_KEY`.

### Run the app

```bash
uvicorn src.main:app --reload
```

## Code quality

Run tests and linters before opening a PR.

```bash
pytest
```

## Pull request process

1. Create a feature branch
2. Keep PRs focused and small when possible
3. Include docs updates when changing behavior
4. Ensure CI is green

## Security

- Do not commit real tokens/secrets.
- Prefer `.env` and secret managers.

## License

By contributing, you agree that your contributions are licensed under the project’s **BSL 1.1** terms.
