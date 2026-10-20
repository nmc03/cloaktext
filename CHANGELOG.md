# Historial de versiones

El formato sigue los principios de Keep a Changelog y las versiones usan SemVer.

## [1.2.0] - 2026-10-20

### Corregido

- **Privacidad:** un IBAN válido seguido de texto (por ejemplo, `ES91 2100 0418 4502 0005 1332 antes del viernes`) no se protegía, y en algunos casos el IBAN arrastraba la palabra siguiente. Ahora se recorta al IBAN válido y se comprueba la longitud oficial del país.
- Los teléfonos fijos españoles con agrupación `91 123 45 67` ahora se detectan (español y catalán).

### Añadido

- **Clave cifrada con contraseña** (opcional): AES-256-GCM con clave derivada por scrypt, autenticada. Las claves antiguas en texto plano siguen funcionando. Nueva dependencia: `cryptography`.
- **Interfaz en 7 idiomas** (español, inglés, francés, alemán, italiano, portugués y catalán) con selector en la cabecera; por defecto sigue el idioma de Windows.
- **Proteger selección**: selecciona texto en la entrada y añádelo a las palabras adicionales con un clic.
- Atestación de procedencia de la compilación (GitHub Actions) para el ZIP de Windows, como alternativa a la firma de código.
- **Resaltado** de los marcadores en el resultado, con interruptor.
- **Palabras adicionales**: términos propios (proyectos, clientes, apodos) que siempre se protegen.
- **Limpieza de entradas antiguas** (menú Clave) con fechas de alta en `cloaktext.dates.json` (sin datos originales).
- Carpeta de datos alternativa (`%LOCALAPPDATA%\CloakText`) cuando la carpeta de la aplicación no admite escritura.
- Pruebas de regresión para IBAN, teléfonos y DNI con letra incorrecta (se protege a propósito).
- Capturas reales en el README y script `scripts/doc_screenshots.py` para regenerarlas.
- `PRIVACY.md`, `README.es.md` y guía de contribución ampliada (inglés y español).

### Cambiado

- **Código en inglés**: identificadores, módulos (`motor_local.py` → `local_engine.py`, `language_models.py` → `language_packs.py`), comentarios y docstrings. No cambia ningún formato persistido (`cloaktext.json`, tipos de marcador, claves de ajustes).
- Pasaportes y NINO solo coinciden en mayúsculas (menos falsos positivos como `abc123456`).
- El NIF portugués valida su dígito de control (antes protegía cualquier número de 9 cifras).
- `anonimizar()` y `analizar_spans()` aceptan un parámetro opcional `terminos`.

- README, SECURITY y CONTRIBUTING reescritos en inglés con versión en español; corrección de erratas de género en SECURITY.

## [1.1.0] - 2026-10-07

Versión de mantenimiento: workflow de compilación para Windows y documentación actualizados.

## [1.0.0] - 2026-10-03

Primera versión preparada para distribución de escritorio.

### Añadido

- Dos acciones de limpieza separadas: Limpiar para los cuadros de texto y Limpiar JSON con confirmación.
- Logo embebido en la interfaz para que también se muestre en el encabezado del ejecutable.

- `cloaktext.json` predeterminado y persistente junto a la aplicación; se actualiza automáticamente y no se muestra en pantalla.
- Exportación de la clave JSON y selección opcional de un JSON personalizado al restaurar.
- Modelos spaCy grandes (`lg`) para los siete idiomas, descargados bajo demanda y verificados por SHA-256.
- Los modelos se guardan en la carpeta portable `models` junto al ejecutable.

- Interfaz responsive orientada a usuarios no técnicos.
- Carga y guardado de claves de restauración en JSON.
- Copia directa del texto protegido y de la clave de restauración.
- Resumen de tipos de datos detectados.
- Preparación guiada de idiomas en el primer uso.
- Soporte de interfaz para español, inglés, francés, alemán, italiano, portugués y catalán.
- Detección estructurada de IPv4 y validación MOD-97 de IBAN.
- Procesamiento por bloques para textos extensos.
- Pruebas automatizadas del motor.
- CI para Linux y compilación reproducible para Windows.
- Paquete Windows portable sin redistribuir modelos lingüísticos de terceros.
- Descarga opcional de modelos spaCy grandes desde el origen oficial con verificación SHA-256.
- Icono y metadatos del ejecutable.

### Cambiado

- Migración de Flet 0.24 a Flet 1.0.
- Actualización a spaCy 3.8.
- Gestión de solapamientos de entidades con menor consumo de memoria.
- Los patrones estructurados tienen prioridad sobre detecciones NER solapadas.
- Manejo de errores y estados de procesamiento más claro.
- El motor evita colisiones con tokens ya presentes en el texto.

### Corregido

- Liberación inmediata del modelo grande anterior al cambiar de idioma, con recolección de memoria forzada.
- Los cuadros de texto ocupan todo el ancho disponible dentro de cada tarjeta.
- La descripción del proceso Windows se muestra como CloakText.

- Filtro conservador de falsos positivos NER para saludos conversacionales obvios como `hola`.

- Compatibilidad de inicio con Flet 1.0.3: el selector de idioma usa `on_select`, el evento admitido por `Dropdown`.
- Prueba de construcción completa de la interfaz para detectar incompatibilidades de API antes de generar el ejecutable.

### Seguridad

- Validación estricta del formato del clave de restauración.
- El modelo no se descarga de memoria mientras está procesando.
- Avisos explícitos sobre la sensibilidad de la clave de restauración.
- Sin mensajes de error internos expuestos al usuario final.

## [0.1.0] - 2026-06-08

- Prototipo inicial de CloakText.
- Anonimización reversible local con Flet y spaCy.
