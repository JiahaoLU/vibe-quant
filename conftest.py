import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: mark test as requiring live network access (run with: pytest -m integration)",
    )
