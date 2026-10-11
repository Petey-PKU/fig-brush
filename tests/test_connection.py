import pytest

import origin_bridge.connection as connection


def test_startup_error_explains_uff_reset_and_restricted_com(monkeypatch):
    class FakeOrigin:
        def set_show(self, show):
            raise RuntimeError("LT_execute: Invalid command")

    monkeypatch.setattr(connection, "_import_originpro", lambda: FakeOrigin())
    with pytest.raises(connection.OriginStartupError, match="User Files Folder"):
        with connection.OriginSession(show=False):
            pass


def test_startup_error_preserves_generic_origin_failure_context(monkeypatch):
    class FakeOrigin:
        def set_show(self, show):
            raise RuntimeError("COM server unavailable")

    monkeypatch.setattr(connection, "_import_originpro", lambda: FakeOrigin())
    with pytest.raises(connection.OriginStartupError, match="COM server unavailable"):
        with connection.OriginSession(show=False):
            pass
