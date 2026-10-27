from types import SimpleNamespace

import pytest

from local_engine import (
    LocalEngine,
    _is_ner_false_positive,
    _is_valid_iban,
    _select_non_overlapping,
    _split_text,
)


class _EmptyUse:
    def __enter__(self):
        return lambda text: SimpleNamespace(ents=[])

    def __exit__(self, exc_type, exc, tb):
        return False


class _EmptyManager:
    def use(self, language):
        return _EmptyUse()


@pytest.fixture
def engine():
    instance = LocalEngine.__new__(LocalEngine)
    instance._manager = _EmptyManager()
    return instance


def test_roundtrip_email_telefono_e_ip(engine):
    original = "Contacto: ana@example.com, +34 612 345 678, IP 192.168.10.4."
    mapping = {}
    protected_text = engine.protect(original, mapping, language="es")

    assert "ana@example.com" not in protected_text
    assert "612 345 678" not in protected_text
    assert "192.168.10.4" not in protected_text
    assert engine.restore(protected_text, mapping) == original


def test_does_not_collide_with_existing_tokens(engine):
    original = "Ya existe [PERSONA_1000]. Escribe a ana@example.com."
    mapping = {}
    result = engine.protect(original, mapping, language="es")

    assert "[EMAIL_1001]" in result
    assert "[PERSONA_1000]" in result


def test_reuses_token_for_same_value(engine):
    original = "ana@example.com y de nuevo ana@example.com"
    mapping = {}
    result = engine.protect(original, mapping, language="es")

    assert result.count("[EMAIL_1000]") == 2
    assert len(mapping) == 1


def test_restore_does_not_reprocess_tokens_inside_the_original_value(engine):
    mapping = {
        "[PERSONA_1000]": "Texto literal [EMAIL_1001]",
        "[EMAIL_1001]": "ana@example.com",
    }
    assert (
        engine.restore("[PERSONA_1000] / [EMAIL_1001]", mapping)
        == "Texto literal [EMAIL_1001] / ana@example.com"
    )


def test_mapping_rejects_invalid_keys_or_values():
    with pytest.raises(ValueError):
        LocalEngine.validate_mapping({"persona": "Ana"})
    with pytest.raises(ValueError):
        LocalEngine.validate_mapping({"[PERSONA_1000]": ["Ana"]})


def test_iban_valid_and_invalid():
    assert _is_valid_iban("ES91 2100 0418 4502 0005 1332")
    assert not _is_valid_iban("ES00 2100 0418 4502 0005 1332")


def test_regex_takes_priority_over_overlapping_ner():
    candidates = [
        (0, 15, "ORG", "ana@example.com", 10),
        (0, 15, "EMAIL", "ana@example.com", 0),
    ]
    assert _select_non_overlapping(candidates) == [
        (0, 15, "EMAIL", "ana@example.com")
    ]


def test_splitting_preserves_text_and_offsets():
    text = "uno dos tres cuatro cinco seis"
    chunks = list(_split_text(text, 10))
    rebuilt = "".join(chunk for _, chunk in chunks)

    assert rebuilt == text
    for offset, chunk in chunks:
        assert text[offset : offset + len(chunk)] == chunk


def test_models_have_pinned_hash_and_url():
    from language_packs import MODEL_INFO
    assert len(MODEL_INFO) == 7
    assert all(len(info.sha256) == 64 for info in MODEL_INFO.values())
    assert all(info.url.startswith("https://github.com/explosion/spacy-models/") for info in MODEL_INFO.values())
    assert all(info.package.endswith("_lg") for info in MODEL_INFO.values())


def test_wheel_extraction_rejects_path_traversal(tmp_path):
    import zipfile
    from language_packs import _safe_extract_wheel
    wheel = tmp_path / "bad.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.writestr("../escape.txt", "no")
    with pytest.raises(ValueError):
        _safe_extract_wheel(wheel, tmp_path / "out")


def test_wheel_extraction_valid(tmp_path):
    import zipfile
    from language_packs import _safe_extract_wheel
    wheel = tmp_path / "ok.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.writestr("modelo/modelo-3.8.0/meta.json", "{}")
    destination = tmp_path / "out"
    _safe_extract_wheel(wheel, destination)
    assert (destination / "modelo" / "modelo-3.8.0" / "meta.json").is_file()


@pytest.mark.parametrize(
    ("language", "text"),
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
def test_obvious_greetings_are_not_entities(language, text):
    assert _is_ner_false_positive(text, language)


def test_unloading_model_forces_garbage_collection(monkeypatch):
    import local_engine

    manager = local_engine.SingleModelManager.__new__(local_engine.SingleModelManager)
    manager._nlp = object()
    manager._language = "es"

    calls = []
    monkeypatch.setattr(local_engine.gc, "collect", lambda: calls.append(True))

    manager._unload_internal()

    assert manager._nlp is None
    assert manager._language is None
    assert calls == [True]


def test_iban_followed_by_text_is_protected_without_swallowing_words(engine):
    original = "Transferir a ES91 2100 0418 4502 0005 1332 antes del viernes"
    mapping = {}
    result = engine.protect(original, mapping, language="es")

    assert "2100" not in result
    assert result.endswith("antes del viernes")
    assert list(mapping.values()) == ["ES91 2100 0418 4502 0005 1332"]


def test_iban_does_not_swallow_trailing_word_even_if_it_validates_by_chance(engine):
    mapping = {}
    result = engine.protect("Cuenta ES91 2100 0418 4502 0005 1332 gracias", mapping, language="es")

    assert result.endswith("gracias")
    assert list(mapping.values()) == ["ES91 2100 0418 4502 0005 1332"]


def test_iban_with_wrong_length_for_its_country_is_rejected():
    assert not _is_valid_iban("ES91 2100 0418 4502 0005 13320")
    assert _is_valid_iban("DE89 3704 0044 0532 0130 00")
    assert _is_valid_iban("GB82 WEST 1234 5698 7654 32")


@pytest.mark.parametrize("phone", ["612345678", "612 345 678", "+34 612 345 678", "91 123 45 67", "912 345 678"])
def test_spanish_mobile_and_landline_phones(engine, phone):
    mapping = {}
    result = engine.protect(f"Llama al {phone} ya", mapping, language="es")

    assert result == "Llama al [TELEFONO_1000] ya"
    assert mapping["[TELEFONO_1000]"] == phone


def test_id_number_with_wrong_letter_is_still_protected(engine):
    # Privacy decision: when in doubt, protect. A mistyped DNI is still personal data.
    mapping = {}
    result = engine.protect("DNI 12345678A", mapping, language="es")
    assert result == "DNI [NIF_1000]"


def test_passport_only_in_uppercase(engine):
    mapping = {}
    result = engine.protect("ref abc123456 y ABC123456", mapping, language="es")
    assert result == "ref abc123456 y [PASAPORTE_1000]"


def test_portuguese_nif_validates_check_digit(engine):
    mapping = {}
    result = engine.protect("NIF 123456789 pedido 123456780", mapping, language="pt")
    assert result == "NIF [NIF_PT_1000] pedido 123456780"


def test_manual_terms_are_protected_and_restored(engine):
    mapping = {}
    original = "Proyecto Atlas con Ana María Pérez. Ana María vuelve; atlas sigue."
    result = engine.protect(original, mapping, language="es", terms=["Atlas", "Ana María", "  ", "atlas"])

    assert "Atlas" not in result and "Ana María" not in result
    assert result.count("[MANUAL_") == 4
    assert engine.restore(result, mapping) == original


def test_manual_terms_respect_word_boundaries(engine):
    mapping = {}
    result = engine.protect("Ana y Anabel", mapping, language="es", terms=["Ana"])
    assert result == "[MANUAL_1000] y Anabel"


def test_manual_terms_with_special_characters(engine):
    mapping = {}
    result = engine.protect("clave (a+b)* aquí", mapping, language="es", terms=["(a+b)*"])
    assert "a+b" not in result


def test_normalize_terms_limits_count_and_length():
    many_terms = [f"t{i}" for i in range(1000)] + ["x" * 500]
    result = LocalEngine.normalize_terms(many_terms)
    assert len(result) == 500
    assert all(len(t) <= 200 for t in result)


@pytest.mark.parametrize("label", ["SSN", "ssn", "DNI", "IBAN", "NIF."])
def test_document_labels_are_not_treated_as_organisations(label):
    assert _is_ner_false_positive(label, "en")
    assert _is_ner_false_positive(label, "es")


@pytest.mark.parametrize(
    ("language", "phone"),
    [
        ("fr", "+33 6 12 34 56 78"),
        ("fr", "06 12 34 56 78"),
        ("fr", "+33 1 23 45 67 89"),
        ("it", "+39 333 123 4567"),
        ("it", "333 123 4567"),
        ("it", "06 12345678"),
        ("de", "+49 151 12345678"),
        ("de", "030 12345678"),
    ],
)
def test_international_and_mobile_phone_formats(engine, language, phone):
    mapping = {}
    result = engine.protect(f"Tel {phone} fin", mapping, language=language)

    assert result == "Tel [TELEFONO_1000] fin"
    assert mapping["[TELEFONO_1000]"] == phone
