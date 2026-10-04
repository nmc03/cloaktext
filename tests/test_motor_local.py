from types import SimpleNamespace

import pytest

from motor_local import (
    MotorLocal,
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
