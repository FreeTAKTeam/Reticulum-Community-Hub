# PLANNING

## Goals

- Provide a stable Reticulum Comunity Hub for LXMF clients.
- Persist telemetry, topics, subscribers, and attachments reliably.
- Keep commands and APIs predictable, backward compatible, and well documented.
- Maintain high test coverage and strong linting to protect behavior.

## Style

- Python 3.10+, PEP 8, `black` formatting, `ruff` linting.
- Use type hints everywhere; avoid implicit `Any`.
- Use `pydantic` for validation and `FastAPI` for APIs when needed.
- Prefer small, single-responsibility functions and classes.
- Write Google-style docstrings for every function and method.
- Add comments only when the "why" is non-obvious.
- Keep files under 500 lines; split by feature or responsibility.

## Constraints

- Use `python_dotenv` and `load_env()` for environment variables.
- Keep test coverage >= 90%.
- Update `pyproject.toml` version (minor bump) for every change.
- Do not use multiple imports on one line.
- Preserve existing behavior unless explicitly requested.
- Avoid new dependencies unless needed and justified.

## Naming Conventions

- Modules: `snake_case.py`.
- Classes: `PascalCase`.
- Functions/methods: `snake_case`.
- Constants: `UPPER_SNAKE_CASE`.
- Pydantic models: `PascalCase` with clear domain names.
- Test files: `test_<module>.py` under `tests/` mirroring package layout.

## File Structure

- `reticulum_telemetry_hub/`
  - `api/` API models, services, and storage.
  - `config/` configuration models and loaders.
  - `lxmf_telemetry/` telemetry capture and persistence.
  - `reticulum_server/` runtime hub, commands, and services.
  - `atak_cot/` TAK integration helpers.
  - `embedded_lxmd/` LXMF daemon integration.
- `tests/` mirrors the package structure.
- `docs/` user and command documentation.
- `API/` OpenAPI and API references.

## Architecture Patterns

- Service layer (`api.service`) orchestrates business logic.
- Storage layer (`api.storage`) handles database interactions.
- Command layer (`reticulum_server.command_manager`) normalizes and routes commands.
- Runtime hub (`reticulum_server.__main__`) wires dependencies and handles IO.
- Configuration is centralized in `config.manager` and immutable models.
- Prefer explicit dependency injection for testability.
