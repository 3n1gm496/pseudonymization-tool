# Improvements & Changelog

**Note:** All improvements and feature details are now consolidated in [RELEASES.md](RELEASES.md).

Please refer to [RELEASES.md](RELEASES.md) for:
- Version history and release notes
- Feature additions
- Bug fixes
- Improvements per release

## Feature Overview

### 1. CI/CD Pipeline with GitHub Actions

**Location:** `.github/workflows/ci.yml`

**Features:**
- Automated testing on every push and pull request
- Python 3.11 matrix build
- Code quality checks (flake8, black, isort)
- Security scanning (bandit, safety)
- Test coverage reporting with pytest-cov
- Codecov integration for coverage tracking

**Usage:**
```bash
# Runs automatically on git push
# View results at: https://github.com/3n1gm496/pseudonymization-tool/actions
```

### 2. Test Coverage with Pytest

**Location:** `backend/tests/`

**New Files:**
- `conftest.py` - Pytest configuration and fixtures
- `test_email_detector.py` - Example unit tests for email detector
- `pyproject.toml` - Pytest and coverage configuration

**Features:**
- Pytest test framework
- Code coverage reporting (XML, HTML, terminal)
- Test fixtures for reusable test data
- Parametrized tests
- Async test support

**Usage:**
```bash
cd backend
pytest tests/ -v --cov=app --cov-report=html
# Open htmlcov/index.html to view coverage report
```

### 3. Pre-commit Hooks

**Location:** `.pre-commit-config.yaml`

**Features:**
- Automatic code formatting with black
- Import sorting with isort
- Linting with flake8
- Security checks with bandit
- JSON/YAML validation
- Private key detection

**Setup:**
```bash
pip install pre-commit
pre-commit install
# Hooks now run automatically on git commit
```

**Manual run:**
```bash
pre-commit run --all-files
```

### 4. Structured Logging

**Location:** `backend/app/core/logging_config.py`

**Features:**
- JSON-formatted logs (production mode)
- Console-formatted logs (development mode)
- Request correlation IDs (X-Request-ID header)
- Automatic request/response logging with timing
- Structured log fields (timestamp, level, context)
- No sensitive data in logs

**Usage:**
```python
from app.core.logging_config import get_logger

logger = get_logger(__name__)
logger.info("processing_file", filename="document.pdf", size_bytes=12345)
```

**Request Logging:**
Every HTTP request is automatically logged with:
- Request ID (correlation)
- HTTP method and path
- Response status code
- Request duration in milliseconds

### 5. Health Check & Monitoring Endpoints

**Location:** `backend/app/api/monitoring.py`

**Endpoints:**

#### GET /api/health
Basic liveness check. Returns 200 if service is running.

Response:
```json
{
  "status": "healthy",
  "timestamp": "2026-02-28T10:30:00",
  "uptime_seconds": 3600.5,
  "version": "1.0.0"
}
```

#### GET /api/ready
Readiness check. Verifies all dependencies are available.

Response:
```json
{
  "ready": true,
  "checks": {
    "filesystem": {"status": "ok", "writable": true},
    "parsers": {"status": "ok", "available": true},
    "ocr": {"status": "warning", "available": false}
  }
}
```

#### GET /api/metrics
Application metrics endpoint.

Response:
```json
{
  "app_uptime_seconds": 3600.5,
  "app_version": "1.0.0",
  "app_name": "pseudonymization-tool",
  "timestamp": "2026-02-28T10:30:00"
}
```

**Usage:**
```bash
# Check health
curl http://localhost:8000/api/health

# Check readiness
curl http://localhost:8000/api/ready

# Get metrics
curl http://localhost:8000/api/metrics
```

## Dependencies

### Production (`backend/requirements.txt`):
- `structlog>=24.1.0` - Structured logging

### Development (`backend/requirements-dev.txt`):
- `pytest>=8.0.0` - Testing framework
- `pytest-cov>=4.1.0` - Coverage plugin
- `pytest-asyncio>=0.23.5` - Async test support
- `pytest-mock>=3.12.0` - Mocking utilities
- `black>=24.2.0` - Code formatter
- `isort>=5.13.2` - Import sorter
- `flake8>=7.0.0` - Linter
- `bandit>=1.7.7` - Security scanner
- `safety>=3.0.1` - Dependency vulnerability scanner
- `mypy>=1.8.0` - Type checker
- `pre-commit>=3.6.0` - Git hooks framework

## Getting Started

### Install Development Dependencies
```bash
cd backend
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### Setup Pre-commit Hooks
```bash
pre-commit install
```

### Run Tests
```bash
cd backend
pytest tests/ -v --cov=app
```

### Run Code Quality Checks
```bash
# Format code
black backend/app

# Sort imports
isort backend/app

# Lint
flake8 backend/app

# Security scan
bandit -r backend/app -ll
```

### Start Application with Structured Logging
```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Monitoring in Production

### Health Check Integration
Use health endpoints for:
- Kubernetes liveness/readiness probes
- Load balancer health checks
- Monitoring systems (Prometheus, DataDog, etc.)

Example Kubernetes probe:
```yaml
livenessProbe:
  httpGet:
    path: /api/health
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /api/ready
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 5
```

### Log Aggregation
Enable JSON logs for production:
```python
# In app/core/logging_config.py
configure_logging(log_level="INFO", json_logs=True)
```

Then use log aggregation tools:
- Elasticsearch + Kibana (ELK stack)
- Splunk
- DataDog
- CloudWatch Logs

### Request Tracing
Every request gets a unique `X-Request-ID` header:
```bash
curl -v http://localhost:8000/api/health
# < X-Request-ID: 550e8400-e29b-41d4-a716-446655440000
```

Use this ID to trace requests across logs and systems.

## Code Coverage Targets

Current coverage target: **80%+**

View coverage report:
```bash
cd backend
pytest tests/ --cov=app --cov-report=html
open htmlcov/index.html
```

## Security Checks

Automated security scanning includes:
- **Bandit**: Python code security issues
- **Safety**: Known vulnerabilities in dependencies
- **Pre-commit hooks**: Private key detection

Run manually:
```bash
bandit -r backend/app -ll
safety check
```

## Next Steps (P1/P2+)

Planned enhancements:
- [ ] Performance optimization (streaming, async processing)
- [ ] API rate limiting distribuito (Redis/shared-state)
- [ ] Advanced metrics (Prometheus format)
- [ ] ML-based entity recognition
- [ ] Frontend modernization (React/Vue)
- [ ] Detector quality loop (false-positive feedback dalla review)
- [ ] Deploy parity con stack container (compose + healthcheck + runbook)

## Contributing

All contributions must pass:
1. Pre-commit hooks
2. Test suite (pytest)
3. Code coverage >= 80%
4. Security scans
5. GitHub Actions CI

See [Contributing Guide](../README.md#contributing) for details.
