# AGENTS.md - Reticulum Community Hub (RCH)

This document provides essential context for AI coding agents working on the Reticulum Community Hub (RCH) / Reticulum Telemetry Hub (RTH) project.

---

## Project Overview

**Reticulum Community Hub (RCH)** is a shared coordination point for mesh networks built on the [Reticulum](https://reticulum.network/) protocol. It enables people and groups to exchange messages, share situational updates, and distribute files in a structured and reliable way, even across intermittent or low-connectivity environments, while remaining independent from centralized internet services.

- **Package Name**: `ReticulumCommunityHub`
- **Current Version**: 1.35.1
- **Python Version**: 3.10+
- **License**: Eclipse Public License (EPL)

### Key Capabilities

- One-to-many and topic-scoped message fan-out over LXMF
- Telemetry collection and on-demand telemetry responses
- File and image attachment storage with retrieval and deletion by ID
- Operator-managed map markers backed by Reticulum object identities
- TAK (Tactical Assault Kit) bridge for chat and location updates
- Zone (polygon) management for operational areas
- Mission and checklist synchronization
- sci-fi themed admin UI with WebSocket real-time updates
- Capability announces embedded in Reticulum announces for feature discovery

---

## Technology Stack

### Backend

| Component | Technology |
|-----------|------------|
| Language | Python 3.10+ |
| Package Management | Poetry |
| API Framework | FastAPI |
| Database ORM | SQLAlchemy 2.0 |
| Database | SQLite (telemetry.db, rth_api.sqlite) |
| Networking | Reticulum (RNS), LXMF |
| Cryptography | PyNaCl, cryptography |
| Serialization | msgpack, PyYAML |
| Testing | pytest, pytest-cov |
| Linting | Ruff |

### Frontend

| Component | Technology |
|-----------|------------|
| Framework | Vue.js 3 (Composition API) |
| Language | TypeScript |
| Build Tool | Vite 6 |
| State Management | Pinia |
| Styling | Tailwind CSS |
| Maps | MapLibre GL |
| Icons | Material Design Icons (MDI) |

### Desktop Packaging

| Component | Technology |
|-----------|------------|
| Shell | Electron 40+ |
| Backend Bundling | PyInstaller |
| Build Scripts | PowerShell (Windows), Bash (Linux/macOS) |

---

## Project Structure

```
Reticulum-Telemetry-Hub/
├── reticulum_telemetry_hub/     # Main Python package
│   ├── api/                     # API service and storage layer
│   │   ├── service.py           # Business logic orchestration
│   │   ├── storage*.py          # Database interaction layers
│   │   └── models.py            # Pydantic/dataclass models
│   ├── atak_cot/                # TAK/CoT integration helpers
│   ├── checklist_sync/          # Checklist synchronization router
│   ├── cli/                     # Command-line interface (rch)
│   │   └── rch.py               # CLI entrypoint (start/stop/status/gateway)
│   ├── config/                  # Configuration management
│   │   ├── manager.py           # Config loader and validator
│   │   ├── models.py            # Config dataclasses
│   │   └── default_config.ini   # Default configuration template
│   ├── embedded_lxmd/           # Embedded LXMF daemon integration
│   ├── internal_api/            # Internal API schemas and adapters
│   │   ├── bus.py               # Internal message bus
│   │   ├── core.py              # Core internal API
│   │   └── v1/                  # API v1 schemas
│   ├── lxmf_daemon/             # Vendored LXMF daemon code
│   ├── lxmf_telemetry/          # Telemetry ingestion and persistence
│   │   ├── telemetry_controller.py
│   │   ├── sampler.py
│   │   └── model/               # Telemetry data models
│   ├── mission_domain/          # Mission domain models and service
│   ├── mission_sync/            # Mission synchronization router
│   ├── northbound/              # FastAPI REST + WebSocket interface
│   │   ├── app.py               # FastAPI app factory
│   │   ├── gateway.py           # Gateway runner (hub + API)
│   │   ├── routes_*.py          # API route modules
│   │   └── websocket.py         # WebSocket broadcasters
│   └── reticulum_server/        # Core hub runtime
│       ├── __main__.py          # Main entrypoint (1000+ lines)
│       ├── command_manager.py   # LXMF command processing
│       ├── services.py          # Hub service definitions
│       └── event_log.py         # Event logging
├── ui/                          # Vue.js frontend
│   ├── src/
│   │   ├── components/          # Vue components
│   │   ├── pages/               # Page components
│   │   ├── stores/              # Pinia stores
│   │   └── api/                 # API client and types
│   └── package.json
├── electron/                    # Electron desktop wrapper
│   ├── package.json
│   ├── src/                     # Electron main process code
│   └── scripts/                 # Build scripts
├── tests/                       # Test suite (mirrors package structure)
├── docs/                        # Documentation
│   ├── architecture.md          # System architecture
│   ├── userManual.md            # User guide
│   └── ...
├── API/                         # OpenAPI specification
│   └── ReticulumCommunityHub-OAS.yaml
├── pyproject.toml               # Python project configuration
├── pytest.ini                 # Test configuration
├── .coveragerc                # Coverage configuration
├── .pylintrc                  # Pylint configuration
└── rch-symbols.yaml           # Marker symbol registry
```

---

## Build and Development Commands

### Python Backend

```bash
# Setup virtual environment (use venv_linux on this machine)
python -m venv venv_linux
venv_linux\Scripts\Activate.ps1  # Windows
source venv_linux/bin/activate   # Linux/macOS

# Install dependencies
python -m pip install -e .

# Run the hub (LXMF only)
python -m reticulum_telemetry_hub.reticulum_server --storage_dir ./RCH_Store --display_name "RCH"

# Run the gateway (hub + API)
python -m reticulum_telemetry_hub.northbound.gateway --data-dir ./RCH_Store --port 8000

# Or use the CLI
rch start --data-dir ./RCH_Store --port 8000 --log-level info
rch status --data-dir ./RCH_Store
rch stop --data-dir ./RCH_Store
```

### UI Development

```bash
cd ui
npm install
npm run dev          # Development server
npm run build        # Production build
npm run lint         # ESLint
npm run test         # Vitest
```

### Electron Desktop Build

```bash
cd electron
npm install

# Development mode
npm run dev

# Build all
npm run dist

# Build Windows only
npm run dist -- --win

# Build Linux (for Raspberry Pi)
npm run dist -- --linux --armv7l
npm run dist -- --linux --arm64
```

### Testing

```bash
# Run all tests with coverage (coverage must be >= 90%)
pytest

# Run specific test file
pytest tests/test_api_models.py

# Run with verbose output
pytest -v

# Update coverage report
pytest --cov=reticulum_telemetry_hub --cov-report=html
```

### Linting

```bash
# Ruff (primary linter)
ruff check .
ruff check . --fix

# Pylint (legacy, limited scope)
pylint reticulum_telemetry_hub/api reticulum_telemetry_hub/config reticulum_telemetry_hub/northbound
```

---

## Code Style Guidelines

### Python

- **Line Length**: 120 characters
- **Formatter**: Black (implicit via Ruff)
- **Linter**: Ruff (replaces flake8)
- **Type Hints**: Required everywhere; avoid implicit `Any`
- **Docstrings**: Google style for every function/method

```python
def example_function(param1: str, param2: int) -> dict[str, Any]:
    """Brief summary of function.

    Args:
        param1: Description of param1.
        param2: Description of param2.

    Returns:
        Description of return value.
    """
    return {"result": param1}
```

### File Organization Rules

1. **Maximum 500 lines per file** - split if approaching limit
2. **Module naming**: `snake_case.py`
3. **Class naming**: `PascalCase`
4. **Function naming**: `snake_case`
5. **Constants**: `UPPER_SNAKE_CASE`
6. **Pydantic models**: `PascalCase` with clear domain names

### Code Architecture Patterns

The codebase follows a layered architecture:

- **Controller** (`controller.py`) - Definition and execution logic
- **Service** (`service.py`) - Exposes functionalities, orchestrates business logic
- **Model** (`model.py`) - Manipulates data
- **Storage** (`storage*.py`) - Handles database interactions

Example module structure:
```python
# api/zone_service.py - Business logic
class ZoneService:
    def create_zone(self, zone: Zone) -> Zone: ...

# api/zone_storage.py - Database interaction
class ZoneStorage:
    def save(self, zone: Zone) -> None: ...

# api/models.py - Data models
class Zone(BaseModel):
    id: str
    name: str
    points: list[ZonePoint]
```

### Import Style

- Prefer relative imports within packages
- One import per line (never multiple imports on one line)
- Group imports: stdlib, third-party, local

```python
# Good
import os
import sys
from pathlib import Path

import RNS
from fastapi import FastAPI

from .models import Zone
from .storage import ZoneStorage

# Bad (multiple imports on one line)
import os, sys, json
```

---

## Testing Requirements

### Coverage Requirements

- **Minimum Coverage**: 90%
- **Coverage Report**: `pytest --cov=reticulum_telemetry_hub --cov-report=term-missing`
- **Omitted from Coverage** (see `.coveragerc`):
  - `lxmf_daemon/*` - Vendored upstream code
  - `atak_cot/pytak_client.py` - External integration
  - `reticulum_server/command_*.py` - Runtime wiring

### Test Structure

Tests mirror the package structure under `tests/`:

```
tests/
├── api/                    # Tests for api/ package
├── northbound/             # Tests for northbound/ package
├── reticulum_server/       # Tests for reticulum_server/
├── conftest.py             # pytest fixtures
└── factories.py            # Test data factories
```

### Test Requirements per Function

Every piece of logic should have tests covering:
1. Expected use case
2. Edge case
3. Failure case

```python
# tests/api/test_zone_service.py
def test_create_zone_success(zone_service):
    """Test creating a valid zone."""
    zone = Zone(name="Test", points=[...])
    result = zone_service.create_zone(zone)
    assert result.id is not None

def test_create_zone_empty_points_raises(zone_service):
    """Test creating zone with no points raises error."""
    zone = Zone(name="Test", points=[])
    with pytest.raises(ValueError):
        zone_service.create_zone(zone)
```

---

## Configuration

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `RTH_STORAGE_DIR` | Storage directory for hub data |
| `RTH_API_KEY` | API key for remote authentication (`RCH_API_KEY` is legacy alias) |
| `RTH_SYMBOL_REGISTRY_PATH` | Override path for `rch-symbols.yaml` |
| `VITE_RTH_BASE_URL` | UI: REST API base URL |
| `VITE_RTH_WS_BASE_URL` | UI: WebSocket base URL |
| `RCH_DATA_DIR` | Electron: Data directory override |
| `RCH_BACKEND_PORT` | Electron: Backend port override |
| `RCH_LOG_LEVEL` | Electron: Log level override |
| `RCH_BACKEND_MANAGED` | Electron: Set `false` to disable autostart |

### Configuration File

The hub uses `config.ini` in the storage directory. Key sections:

- `[app]` - Application metadata
- `[hub]` - Hub behavior (announce intervals, logging)
- `[announce.capabilities]` - Capability announcement settings
- `[reticulum]` - Reticulum transport settings
- `[interfaces]` - Network interface configuration
- `[propagation]` - LXMF propagation node settings
- `[TAK]` - TAK server integration
- `[telemetry]` - Telemetry sensor enablement

---

## Security Considerations

### API Authentication

- Remote clients **must authenticate** with API key
- API key via header: `X-API-Key: <key>` or `Authorization: Bearer <key>`
- Loopback/local requests from same machine allowed without credentials
- Set `RTH_API_KEY` environment variable before starting hub

### Identity Encryption

- Marker identity encryption derived from hub identity
- No extra key configuration required
- Uses `derive_marker_identity_key()` from hub identity material

### Data Validation

- All inputs validated via Pydantic models
- File paths sanitized before filesystem operations
- SQL injection prevention via SQLAlchemy parameterized queries

---

## Deployment Processes

### PyPI Package

```bash
# Build and publish
poetry build
poetry publish
```

### Electron Desktop App

1. **Synchronize version** from `pyproject.toml` to `electron/package.json`
2. **Build UI**: `npm run build:ui` (produces `ui/dist/`)
3. **Build Electron**: `npm run build:electron` (compiles TypeScript)
4. **Build Backend**: `npm run build:backend` (PyInstaller bundles Python)
5. **Package**: `npm run dist` (electron-builder creates installers)

Windows artifacts:
- Installer: `RCH_win Install_<version>.exe`
- Portable: `RCH_win Portable_<version>.exe`

### Docker/Container Considerations

The project does not currently include Docker configurations. When adding:
- Use multi-stage builds to reduce image size
- Mount storage directory as volume
- Expose port 8000 for API
- Consider Reticulum interface requirements

---

## Key Dependencies and Integration Points

### Reticulum/LXMF

- **RNS** (Reticulum Network Stack): Core mesh networking
- **LXMF**: Lightweight Extensible Message Format
- **lxmf_daemon/**: Vendored LXMF daemon (do not modify style)

### TAK Integration

- **PyTAK**: TAK client library
- Converts LXMF chat to CoT (Cursor on Target) events
- Supports TCP unicast to TAK servers
- Keepalive with `takPong` messages

### Database Schema

- **telemetry.db**: SQLite for telemetry streams
- **rth_api.sqlite**: SQLite for hub data (topics, subscribers, files, markers, zones)

### WebSocket Events

Real-time events broadcast via WebSocket:
- `event` - General hub events
- `telemetry` - Telemetry updates
- `message` - Chat messages

---

## Development Workflow

### Before Starting Work

1. **Read `PLANNING.md`** for architecture and constraints
2. **Check `TASK.md`** for current tasks and context
3. **Verify file paths** exist before referencing

### During Development

1. **Add tests** for every new feature/function
2. **Run linting**: `ruff check .`
3. **Run tests**: `pytest` (ensure coverage >= 90%)
4. **Update version** in `pyproject.toml` (minor bump for features, patch for fixes)
5. **Sync versions** to `ui/package.json` and `electron/package.json`

### Before Committing

1. **All tests pass**
2. **Coverage >= 90%**
3. **Ruff linting passes**
4. **Google-style docstrings present**
5. **Type hints complete**
6. **MUST test the code before declaring it's done** - For UI changes, verify the component renders without errors; for backend changes, verify the endpoint/function works as expected. Do not rely solely on automated tests.

### Task Completion

- Mark completed tasks in `TASK.md`
- Add discovered TODOs under "Discovered During Work" section
- Update `README.md` if features or setup changed

---

## Common Issues and Solutions

### LXMF Daemon Import Issues

The `lxmf_daemon` package is vendored from upstream. Import order matters:

```python
# Correct order for LXMF imports
import LXMF
import RNS
# Then local imports
```

### Reticulum Instance Singleton

RNS enforces a single Reticulum instance per process. Tests reuse the existing instance:

```python
existing_reticulum = RNS.Reticulum.get_instance()
if existing_reticulum is not None:
    self.ret = existing_reticulum
else:
    self.ret = RNS.Reticulum(...)
```

### Database Session Management

Always use context managers for database sessions:

```python
with self.storage.session() as session:
    result = session.query(Model).all()
    # Session auto-commits on success, rolls back on exception
```

---

## Documentation References

- `docs/architecture.md` - System architecture and data flows
- `docs/userManual.md` - User and operator guide
- `docs/internal-api.md` - Internal API contract
- `docs/TelemetryDocumentation.md` - Telemetry wire format
- `docs/tak.md` - TAK integration details
- `API/ReticulumCommunityHub-OAS.yaml` - REST/OpenAPI specification
- `ui/README.md` - UI development guide

---

## Contact and Support

- **Issues**: GitHub Issues
- **License**: Eclipse Public License (EPL)
- **Upstream**: Reticulum (https://reticulum.network/)
