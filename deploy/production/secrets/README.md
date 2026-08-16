# Production secrets boundary

The production Compose file accepts a runtime environment file through
`ODIRAG_RUNTIME_ENV_FILE`. The deployment target should keep that file outside
the repository, owned by `root:root` (or the dedicated deploy group), mode
`0600`, for example `/etc/odirag/production.env`.

Never commit a runtime environment file, paste secret values into a report, or
mount the developer `backend/.env` into a production container. Provider keys
are optional at process startup but are required for the corresponding live
retrieval, rerank, generation, or discovery smoke test.
