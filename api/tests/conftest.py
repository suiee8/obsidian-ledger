from fastapi.testclient import TestClient

# The API requires `X-Ledger-Client` on writes, as the web app sends. Patched at import time
# so module-scoped fixtures that build clients get it too.
_original_init = TestClient.__init__


def _init(self: TestClient, *args: object, **kwargs: object) -> None:
    _original_init(self, *args, **kwargs)  # type: ignore[arg-type]
    self.headers.setdefault("X-Ledger-Client", "web")


TestClient.__init__ = _init  # type: ignore[method-assign]
