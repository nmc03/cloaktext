from types import SimpleNamespace

import pytest

from motor_local import (
    MotorLocal,
    _es_falso_positivo_ner,
    _iban_valido,
    _seleccionar_no_solapados,
    _trocear_texto,
)


class _UsoVacio:
    def __enter__(self):
        return lambda texto: SimpleNamespace(ents=[])

    def __exit__(self, exc_type, exc, tb):
        return False


class _GestorVacio:
    def usar(self, idioma):
        return _UsoVacio()


@pytest.fixture
def motor():
    instancia = MotorLocal.__new__(MotorLocal)
    instancia._gestor = _GestorVacio()
    return instancia


def test_roundtrip_email_telefono_e_ip(motor):
    original = "Contacto: ana@example.com, +34 612 345 678, IP 192.168.10.4."
    mapa = {}
    anonimizado = motor.anonimizar(original, mapa, idioma="es")

    assert "ana@example.com" not in anonimizado
    assert "612 345 678" not in anonimizado
    assert "192.168.10.4" not in anonimizado
    assert motor.desanonimizar(anonimizado, mapa) == original


def test_no_colisiona_con_tokens_ya_presentes(motor):
    original = "Ya existe [PERSONA_1000]. Escribe a ana@example.com."
    mapa = {}
    resultado = motor.anonimizar(original, mapa, idioma="es")

    assert "[EMAIL_1001]" in resultado
    assert "[PERSONA_1000]" in resultado


def test_reutiliza_token_para_mismo_valor(motor):
    original = "ana@example.com y de nuevo ana@example.com"
    mapa = {}
    resultado = motor.anonimizar(original, mapa, idioma="es")

    assert resultado.count("[EMAIL_1000]") == 2
    assert len(mapa) == 1


def test_desanonimizar_no_reprocesa_tokens_dentro_del_valor_original(motor):
    mapa = {
        "[PERSONA_1000]": "Texto literal [EMAIL_1001]",
        "[EMAIL_1001]": "ana@example.com",
    }
    assert (
        motor.desanonimizar("[PERSONA_1000] / [EMAIL_1001]", mapa)
        == "Texto literal [EMAIL_1001] / ana@example.com"
    )


def test_mapa_rechaza_claves_o_valores_no_validos():
    with pytest.raises(ValueError):
        MotorLocal.validar_mapa({"persona": "Ana"})
    with pytest.raises(ValueError):
        MotorLocal.validar_mapa({"[PERSONA_1000]": ["Ana"]})


def test_iban_valido_y_falso():
    assert _iban_valido("ES91 2100 0418 4502 0005 1332")
    assert not _iban_valido("ES00 2100 0418 4502 0005 1332")


def test_prioriza_regex_frente_a_ner_solapado():
    candidatos = [
        (0, 15, "ORG", "ana@example.com", 10),
        (0, 15, "EMAIL", "ana@example.com", 0),
    ]
    assert _seleccionar_no_solapados(candidatos) == [
        (0, 15, "EMAIL", "ana@example.com")
    ]


def test_troceado_preserva_texto_y_offsets():
    texto = "uno dos tres cuatro cinco seis"
    bloques = list(_trocear_texto(texto, 10))
    reconstruido = "".join(bloque for _, bloque in bloques)

    assert reconstruido == texto
    for offset, bloque in bloques:
        assert texto[offset : offset + len(bloque)] == bloque


def test_modelos_tienen_hash_y_url_fijados():
    from language_models import MODEL_INFO
    assert len(MODEL_INFO) == 7
    assert all(len(info.sha256) == 64 for info in MODEL_INFO.values())
    assert all(info.url.startswith("https://github.com/explosion/spacy-models/") for info in MODEL_INFO.values())
    assert all(info.package.endswith("_lg") for info in MODEL_INFO.values())


def test_extraer_wheel_rechaza_path_traversal(tmp_path):
    import zipfile
    from language_models import _extraer_wheel_seguro
    wheel = tmp_path / "bad.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.writestr("../escape.txt", "no")
    with pytest.raises(ValueError):
        _extraer_wheel_seguro(wheel, tmp_path / "out")


def test_extraer_wheel_valido(tmp_path):
    import zipfile
    from language_models import _extraer_wheel_seguro
    wheel = tmp_path / "ok.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.writestr("modelo/modelo-3.8.0/meta.json", "{}")
    destino = tmp_path / "out"
    _extraer_wheel_seguro(wheel, destino)
    assert (destino / "modelo" / "modelo-3.8.0" / "meta.json").is_file()


@pytest.mark.parametrize(
    ("idioma", "texto"),
    [
        ("es", "hola"),
        ("es", "Hola!"),
        ("en", "hello"),
        ("fr", "bonjour"),
        ("de", "hallo"),
        ("it", "ciao"),
        ("pt", "olá"),
        ("ca", "hola"),
    ],
)
def test_saludos_obvios_no_se_tratan_como_entidades(idioma, texto):
    assert _es_falso_positivo_ner(texto, idioma)


def test_descargar_modelo_fuerza_recoleccion_de_memoria(monkeypatch):
    import motor_local

    gestor = motor_local.GestorModeloUnico.__new__(motor_local.GestorModeloUnico)
    gestor._nlp = object()
    gestor._idioma = "es"

    llamadas = []
    monkeypatch.setattr(motor_local.gc, "collect", lambda: llamadas.append(True))

    gestor._descargar_interno()

    assert gestor._nlp is None
    assert gestor._idioma is None
    assert llamadas == [True]


def test_iban_seguido_de_texto_se_protege_sin_consumir_palabras(motor):
    original = "Transferir a ES91 2100 0418 4502 0005 1332 antes del viernes"
    mapa = {}
    resultado = motor.anonimizar(original, mapa, idioma="es")

    assert "2100" not in resultado
    assert resultado.endswith("antes del viernes")
    assert list(mapa.values()) == ["ES91 2100 0418 4502 0005 1332"]


def test_iban_no_consume_palabra_final_aunque_validara_por_azar(motor):
    mapa = {}
    resultado = motor.anonimizar("Cuenta ES91 2100 0418 4502 0005 1332 gracias", mapa, idioma="es")

    assert resultado.endswith("gracias")
    assert list(mapa.values()) == ["ES91 2100 0418 4502 0005 1332"]


def test_iban_con_longitud_incorrecta_para_su_pais_no_se_acepta():
    assert not _iban_valido("ES91 2100 0418 4502 0005 13320")
    assert _iban_valido("DE89 3704 0044 0532 0130 00")
    assert _iban_valido("GB82 WEST 1234 5698 7654 32")


@pytest.mark.parametrize("telefono", ["612345678", "612 345 678", "+34 612 345 678", "91 123 45 67", "912 345 678"])
def test_telefonos_espanoles_moviles_y_fijos(motor, telefono):
    mapa = {}
    resultado = motor.anonimizar(f"Llama al {telefono} ya", mapa, idioma="es")

    assert resultado == "Llama al [TELEFONO_1000] ya"
    assert mapa["[TELEFONO_1000]"] == telefono


def test_dni_con_letra_incorrecta_tambien_se_protege(motor):
    # Decisión de privacidad: ante la duda, proteger. Un DNI mal tecleado sigue siendo un dato personal.
    mapa = {}
    resultado = motor.anonimizar("DNI 12345678A", mapa, idioma="es")
    assert resultado == "DNI [NIF_1000]"


def test_pasaporte_solo_en_mayusculas(motor):
    mapa = {}
    resultado = motor.anonimizar("ref abc123456 y ABC123456", mapa, idioma="es")
    assert resultado == "ref abc123456 y [PASAPORTE_1000]"


def test_nif_portugues_valida_digito_de_control(motor):
    mapa = {}
    resultado = motor.anonimizar("NIF 123456789 pedido 123456780", mapa, idioma="pt")
    assert resultado == "NIF [NIF_PT_1000] pedido 123456780"


def test_terminos_manuales_se_protegen_y_restauran(motor):
    mapa = {}
    original = "Proyecto Atlas con Ana María Pérez. Ana María vuelve; atlas sigue."
    resultado = motor.anonimizar(original, mapa, idioma="es", terminos=["Atlas", "Ana María", "  ", "atlas"])

    assert "Atlas" not in resultado and "Ana María" not in resultado
    assert resultado.count("[MANUAL_") == 4
    assert motor.desanonimizar(resultado, mapa) == original


def test_terminos_manuales_respetan_limites_de_palabra(motor):
    mapa = {}
    resultado = motor.anonimizar("Ana y Anabel", mapa, idioma="es", terminos=["Ana"])
    assert resultado == "[MANUAL_1000] y Anabel"


def test_terminos_manuales_con_caracteres_especiales(motor):
    mapa = {}
    resultado = motor.anonimizar("clave (a+b)* aquí", mapa, idioma="es", terminos=["(a+b)*"])
    assert "a+b" not in resultado


def test_normalizar_terminos_limita_cantidad_y_longitud():
    muchos = [f"t{i}" for i in range(1000)] + ["x" * 500]
    resultado = MotorLocal.normalizar_terminos(muchos)
    assert len(resultado) == 500
    assert all(len(t) <= 200 for t in resultado)
