from ephyorm.core.main import EphyormCore

def test_core_init():
    core = EphyormCore()
    assert core.initialized is True
