# Contributing

ODIRAG uses small, evidence-backed changes. Preserve the dependency direction
`API -> services -> repositories/providers -> infrastructure`, keep external failures honest, and
do not introduce fabricated retrieval, evaluation, health, or dashboard results.

## Setup

Use Python 3.11+ and Node.js 22+. For a host checkout:

```bash
cd backend
python -m pip install -e ".[dev]"
cd ../frontend
npm ci
```

Copy `.env.example` to `.env` only for local use. Never commit the resulting file or credentials.

## Required Checks

```bash
cd backend
python -m ruff check app tests
python -m black --check app tests
python -m mypy app
python -m pytest --cov=app --cov-report=term-missing

cd ../frontend
npm run lint
npm run type-check
npm test
npm run build
```

Run focused tests while developing and the complete suite at checkpoints. Changes to prompts,
chunking, embedding, retrieval, reranking, routing, grounding, citations, or refusal must run the
focused deterministic benchmark and, when production answer quality can change and the required
live environment is available, the current 100-question Gold evaluation and quality guard. Any
external check that did not run must be reported as `UNVERIFIED`. Migration changes require fresh
upgrade and downgrade/upgrade smoke checks.

## Change Rules

- Reuse existing schemas, protocols, services, and repository patterns.
- Add migrations for persistent schema changes; do not rely on `create_all` in production.
- Keep API errors in the structured envelope and avoid exposing provider/internal details.
- Bind citations only to stored document and chunk identities.
- Add tests proportional to blast radius, including failure and idempotency paths.
- Update `IMPLEMENTATION_STATUS.md`, `CHANGELOG.md`, and affected docs with commands actually run.
- Keep generated indexes, reports, local databases, secrets, and provider responses out of Git.

## Pull Requests

Describe the behavior change, risk, migrations, configuration changes, commands run, test results,
coverage impact, and any external integration that was not executable. Do not mark a Docker,
provider, real-site, or performance check as passed unless it actually ran in that environment.

## Security

Do not open a public issue containing exploitable details or credentials. Follow `SECURITY.md` and
contact the repository owner privately until a dedicated security contact is published.
