# Contributing to Pseudonymization Tool

First off, thank you for considering contributing to this project! Your help is greatly appreciated.

This document provides guidelines for contributing to the project. Please read it carefully to ensure a smooth and effective collaboration process.

## Code of Conduct

This project and everyone participating in it is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior.

## How Can I Contribute?

### Reporting Bugs

If you find a bug, please ensure the bug was not already reported by searching on GitHub under [Issues](https://github.com/3n1gm496/pseudonymization-tool/issues). If you're unable to find an open issue addressing the problem, [open a new one](https://github.com/3n1gm496/pseudonymization-tool/issues/new). Be sure to include a **title and clear description**, as much relevant information as possible, and a **code sample or an executable test case** demonstrating the expected behavior that is not occurring.

### Suggesting Enhancements

If you have an idea for an enhancement, please open an issue to discuss it. This allows us to coordinate our efforts and prevent duplication of work.

### Pull Requests

We welcome pull requests! For major changes, please open an issue first to discuss what you would like to change.

1.  Fork the repo and create your branch from `main`.
2.  If you've added code that should be tested, add tests.
3.  If you've changed APIs, update the documentation.
4.  Ensure the test suite passes (`pytest`).
5.  Make sure your code lints (`black`, `isort`, `eslint`).
6.  Issue that pull request!

## Development Setup

### Prerequisites

-   Python 3.11+
-   Node.js 22+
-   Docker and Docker Compose

### Installation

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/3n1gm496/pseudonymization-tool.git
    cd pseudonymization-tool
    ```

2.  **Backend Setup:**

    ```bash
    cd backend
    python3.11 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    pip install -r requirements-dev.txt
    ```

3.  **Frontend Setup:**

    ```bash
    cd ../frontend
    npm install
    ```

### Running the Application

The easiest way to run the full application stack (backend, frontend, Redis, Celery worker) is with Docker Compose:

```bash
cp .env.example .env
# Edit .env with your desired settings
docker-compose up --build
```

The application will be available at `http://localhost:5173`.

## Testing

-   **Backend:** Run `pytest` from the `backend/` directory.
-   **Frontend:** Run `npm test` from the `frontend/` directory.

## Code Style

-   **Backend:** We use `black` for code formatting and `isort` for import sorting. Please run them before committing your changes:

    ```bash
    black app/ tests/
    isort app/ tests/
    ```

-   **Frontend:** We use `ESLint` for code linting. Please run it before committing your changes:

    ```bash
    npx eslint src/ --ext .jsx,.js
    ```

## Final Notes

Thank you for your contribution!
