from importlib import import_module

import pytest

SERVICE_MODULES = [
    "observer",
    "feature",
    "strategy",
    "policy_risk",
    "executor",
    "evaluator",
    "learner",
    "supervisor",
]


def test_service_modules_expose_service_names():
    for module_name in SERVICE_MODULES:
        module = import_module(f"affiliate_agent.services.{module_name}")
        assert module.SERVICE_NAME == module_name


def test_all_service_modules_are_registered():
    services = import_module("affiliate_agent.services")
    assert services.ALL_SERVICES == SERVICE_MODULES
