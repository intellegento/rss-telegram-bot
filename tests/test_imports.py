import importlib

import pytest


@pytest.mark.parametrize("module", [
    "config",
    "database",
    "utils",
    "news_sources.rss_handler",
    "news_sources.binance_handler",
    "main",
])
def test_module_imports(module):
    importlib.import_module(module)
