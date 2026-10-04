# Contribuir

Los informes de errores y propuestas de mejora son bienvenidos. No incluyas datos personales reales ni claves de restauración en ejemplos públicos.

## Entorno de desarrollo

    python -m venv .venv
    python -m pip install -r requirements-dev.txt
    python -m pytest

Para probar la detección lingüística real, prepara el idioma desde la propia aplicación o instala manualmente el modelo spaCy correspondiente en el entorno de desarrollo.

Antes de proponer un cambio, comprueba:

    python -m pytest
    python -m compileall -q main.py motor_local.py version.py
    python -m pip check

Mantén los cambios centrados en un único objetivo y añade pruebas cuando cambie el comportamiento.
