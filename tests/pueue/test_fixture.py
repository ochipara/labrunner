import pytest
from labrunner.pueue import PueueAdapter

def test_pueue_fixture_health(pueue_env):
    adapter = pueue_env.adapter
    health = adapter.health()
    assert health.daemon_running is True
