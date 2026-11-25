"""Runner mínimo sin dependencias: ejecuta todas las funciones test_* del paquete tests.

Uso:  python tests/run_tests.py
Compatible también con `pytest` si está instalado.
"""

import importlib
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    modules = ["tests.test_engine", "tests.test_store_export"]
    total = failed = 0
    failures = []

    for name in modules:
        mod = importlib.import_module(name)
        for attr in sorted(dir(mod)):
            if not attr.startswith("test_"):
                continue
            fn = getattr(mod, attr)
            if not callable(fn):
                continue
            total += 1
            try:
                fn()
                print(f"  ok   {attr}")
            except Exception:
                failed += 1
                failures.append((attr, traceback.format_exc()))
                print(f"  FAIL {attr}")

    print(f"\n{total - failed}/{total} pruebas OK")
    for name, tb in failures:
        print("\n" + "=" * 70)
        print(name)
        print(tb)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
