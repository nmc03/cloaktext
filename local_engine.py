"""Local reversible protection engine for CloakText.

All processing happens on this machine. The engine keeps at most one spaCy
model loaded, processes long texts in chunks, and prefers structured identifiers
(email, IBAN, phone...) over NER entities when both detectors overlap.
"""

from __future__ import annotations

import gc
from bisect import bisect_left
import logging
import re
import threading
import time
from typing import Callable, Iterable, Optional

import spacy

from i18n import tr

from language_packs import (
    SUPPORTED_LANGUAGES,
    SPACY_MODELS,
    install_model as install_language_package,
    model_available as language_package_available,
    local_model_path,
)

logger = logging.getLogger(__name__)

MAX_NLP_CHARS = 200_000
MAX_MANUAL_TERMS = 500
MAX_TERM_LENGTH = 200
MAX_MAPPING_ENTRIES = 100_000
TOKEN_RE = re.compile(r"\[[A-Z][A-Z0-9_]*_(\d+)\]")

COMMON_PATTERNS = {
    "EMAIL": r"\b[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+\b",
    "IBAN": r"\b[A-Z]{2}\d{2}(?:[\s-]?[A-Z0-9]){11,30}\b",
    "IP": r"\b(?:(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\b",
}

PATTERNS_BY_LANGUAGE = {
    "es": {
        "NIF": r"\b\d{8}[A-HJ-NP-TV-Z]\b",
        "NIE": r"\b[XYZ]\d{7}[A-Z]\b",
        "TELEFONO": r"(?<!\d)(?:\+34[\s\-]?)?(?:[6789]\d{2}[\s\-]?\d{3}[\s\-]?\d{3}|[6789]\d[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2})(?!\d)",
        "PASAPORTE": r"\b[A-Z]{3}\d{6}\b",
        "FECHA_NAC": r"\b(?:0?[1-9]|[12]\d|3[01])[/\-.](?:0?[1-9]|1[0-2])[/\-.](?:19|20)\d{2}\b",
    },
    "en": {
        "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
        "NINO": r"\b[A-Z]{2}\d{6}[A-D]\b",
        "TELEFONO": r"(?<!\d)(?:\+1[\s\-]?)?\(?\d{3}\)?[\s\-]\d{3}[\s\-]\d{4}(?!\d)",
        "FECHA_NAC": r"\b(?:0?[1-9]|1[0-2])[/\-.](?:0?[1-9]|[12]\d|3[01])[/\-.](?:19|20)\d{2}\b",
        "PASAPORTE": r"\b[A-Z]{2}\d{7}\b",
    },
    "fr": {
        "NIR": r"\b[12]\d{2}(?:0[1-9]|1[0-2])\d{5}\d{3}\d{2}\b",
        "TELEFONO": r"(?<!\d)(?:\+33[\s\-]?)?0[1-9](?:[\s\-]?\d{2}){4}(?!\d)",
        "FECHA_NAC": r"\b(?:0?[1-9]|[12]\d|3[01])[/\-.](?:0?[1-9]|1[0-2])[/\-.](?:19|20)\d{2}\b",
        "PASAPORTE": r"\b\d{2}[A-Z]{2}\d{5}\b",
    },
    "de": {
        "STEUER": r"\b\d{2}[\s\/]\d{3}[\s\/]\d{5}\b",
        "TELEFONO": r"(?<!\d)(?:\+49[\s\-]?)?0\d{2,4}[\s\-]?\d{3,8}(?!\d)",
        "FECHA_NAC": r"\b(?:0?[1-9]|[12]\d|3[01])[.\-](?:0?[1-9]|1[0-2])[.\-](?:19|20)\d{2}\b",
        "PASAPORTE": r"\b[CFGHJKLMNPRTVWXYZ][A-Z0-9]{8}\b",
    },
    "it": {
        "CF": r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b",
        "TELEFONO": r"(?<!\d)(?:\+39[\s\-]?)?0\d{1,3}[\s\-]?\d{6,8}(?!\d)",
        "FECHA_NAC": r"\b(?:0?[1-9]|[12]\d|3[01])[/\-.](?:0?[1-9]|1[0-2])[/\-.](?:19|20)\d{2}\b",
        "PASAPORTE": r"\b[A-Z]{2}\d{7}\b",
    },
    "pt": {
        "NIF_PT": r"\b\d{9}\b",
        "TELEFONO": r"(?<!\d)(?:\+351[\s\-]?)?[29]\d{8}(?!\d)",
        "FECHA_NAC": r"\b(?:0?[1-9]|[12]\d|3[01])[/\-.](?:0?[1-9]|1[0-2])[/\-.](?:19|20)\d{2}\b",
        "PASAPORTE": r"\b[A-Z]{2}\d{6}\b",
    },
    "ca": {
        "NIF": r"\b\d{8}[A-HJ-NP-TV-Z]\b",
        "NIE": r"\b[XYZ]\d{7}[A-Z]\b",
        "TELEFONO": r"(?<!\d)(?:\+34[\s\-]?)?(?:[6789]\d{2}[\s\-]?\d{3}[\s\-]?\d{3}|[6789]\d[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2})(?!\d)",
        "FECHA_NAC": r"\b(?:0?[1-9]|[12]\d|3[01])[/\-.](?:0?[1-9]|1[0-2])[/\-.](?:19|20)\d{2}\b",
    },
}

# Official IBAN length per country (SWIFT registry). If the country is known, the
# length must match exactly; otherwise 15-34 characters are accepted.
IBAN_LENGTH_BY_COUNTRY = {
    "AD": 24, "AT": 20, "BE": 16, "BG": 22, "CH": 21, "CY": 28, "CZ": 24,
    "DE": 22, "DK": 18, "EE": 20, "ES": 24, "FI": 18, "FR": 27, "GB": 22,
    "GR": 27, "HR": 21, "HU": 28, "IE": 22, "IS": 26, "IT": 27, "LI": 21,
    "LT": 20, "LU": 20, "LV": 21, "MC": 27, "MT": 31, "NL": 18, "NO": 15,
    "PL": 28, "PT": 25, "RO": 24, "SE": 24, "SI": 19, "SK": 24, "SM": 27,
    "VA": 22,
}

# Types whose pattern mixes letters and digits and would produce too many false
# positives if lowercase were accepted (e.g. "abc123456"). The rest ignore case.
UPPERCASE_ONLY_TYPES = frozenset({"PASAPORTE", "NINO"})

# Types that must also pass a validation in addition to matching the pattern.
VALIDATORS: dict[str, "Callable[[str], bool]"] = {}

SPACY_LABELS = {"PER": "PERSONA", "PERSON": "PERSONA", "LOC": "LUGAR", "GPE": "LUGAR", "ORG": "ORG"}

NER_FALSE_POSITIVES_BY_LANGUAGE = {
    "es": {"hola", "gracias", "adiós", "buenos días", "buenas tardes", "buenas noches"},
    "en": {"hello", "hi", "thanks", "thank you", "goodbye"},
    "fr": {"bonjour", "salut", "merci", "au revoir"},
    "de": {"hallo", "danke", "tschüss", "guten morgen", "guten tag", "guten abend"},
    "it": {"ciao", "grazie", "buongiorno", "buonasera"},
    "pt": {"olá", "oi", "obrigado", "obrigada", "bom dia", "boa tarde", "boa noite"},
    "ca": {"hola", "gràcies", "adéu", "bon dia", "bona tarda", "bona nit"},
}


def _is_ner_false_positive(value: str, language: str) -> bool:
    normalized = " ".join(value.casefold().strip().strip(".,;:!?¡¿").split())
    return normalized in NER_FALSE_POSITIVES_BY_LANGUAGE.get(language, set())


class ModelUnavailableError(ValueError):
    def __init__(self, language: str, model: str):
        self.language = language
        self.model = model
        super().__init__(f"The language model '{model}' is not available.")


class SingleModelManager:
    """Keeps at most one spaCy model loaded in memory."""

    def __init__(self, ttl_minutes: int = 20):
        self._nlp: Optional[spacy.language.Language] = None
        self._language: Optional[str] = None
        self._last_use = 0.0
        self._in_use = 0
        self._lock = threading.Condition()
        self._ttl = max(1, ttl_minutes) * 60
        self._stopping = False
        self._thread = threading.Thread(target=self._cleanup_loop, daemon=True, name="cloaktext-model-ttl")
        self._thread.start()

    def loaded_language(self) -> Optional[str]:
        with self._lock:
            return self._language

    def use(self, language: str):
        return _ModelUse(self, language)

    def unload(self) -> bool:
        """Release the model if it is not processing. Return True if it was freed."""
        with self._lock:
            if self._in_use:
                return False
            self._unload_internal()
            return True

    def stop(self) -> None:
        with self._lock:
            self._stopping = True
            if self._in_use == 0:
                self._unload_internal()
            self._lock.notify_all()

    def _acquire(self, language: str):
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {language}")

        with self._lock:
            while self._language is not None and self._language != language and self._in_use > 0:
                self._lock.wait()

            if self._language != language:
                self._unload_internal()
                self._load(language)

            self._last_use = time.monotonic()
            self._in_use += 1
            return self._nlp

    def _release(self) -> None:
        with self._lock:
            self._in_use = max(0, self._in_use - 1)
            self._last_use = time.monotonic()
            self._lock.notify_all()

    def _load(self, language: str) -> None:
        name = SPACY_MODELS[language]
        logger.info("Loading spaCy model: %s", name)
        try:
            self._nlp = spacy.load(name)
        except OSError:
            file_path = local_model_path(language)
            if file_path is None:
                raise ModelUnavailableError(language, name)
            self._nlp = spacy.load(file_path)

        self._language = language
        self._last_use = time.monotonic()
        logger.info("Model ready: %s", name)

    def _unload_internal(self) -> None:
        previous = self._nlp
        if previous is not None:
            logger.info("Unloading model from memory: %s", SPACY_MODELS.get(self._language))
        self._nlp = None
        self._language = None
        if previous is not None:
            del previous
            gc.collect()

    def _cleanup_loop(self) -> None:
        while True:
            with self._lock:
                if self._stopping:
                    return
                self._lock.wait(timeout=30)
                if self._stopping:
                    return
                if (
                    self._language is not None
                    and self._in_use == 0
                    and time.monotonic() - self._last_use > self._ttl
                ):
                    self._unload_internal()


class _ModelUse:
    def __init__(self, manager: SingleModelManager, language: str):
        self._manager = manager
        self._language = language

    def __enter__(self) -> spacy.language.Language:
        return self._manager._acquire(self._language)

    def __exit__(self, exc_type, exc, tb):
        self._manager._release()
        return False


class LocalEngine:
    def __init__(self, ttl_minutes: int = 20):
        self._manager = SingleModelManager(ttl_minutes=ttl_minutes)

    def loaded_language(self) -> Optional[str]:
        return self._manager.loaded_language()

    def unload_model(self) -> bool:
        return self._manager.unload()

    @staticmethod
    def model_available(language: str) -> bool:
        return language_package_available(language)

    @staticmethod
    def install_model(language: str, progress=None):
        return install_language_package(language, progress)

    def stop(self) -> None:
        self._manager.stop()

    def protect(
        self,
        text: str,
        mapping: dict[str, str],
        filters: Optional[set[str]] = None,
        language: str = "es",
        terms: Optional[Iterable[str]] = None,
    ) -> str:
        if not text or not text.strip():
            return text
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {language}")

        self.validate_mapping(mapping)
        active_types = filters if filters is not None else self._all_types(language)
        spans = self._collect_spans(text, active_types, language, terms)
        next_seq = self._next_sequence(text, mapping)

        value_to_token = {value: token for token, value in mapping.items()}

        def token_for(kind: str, value: str) -> str:
            nonlocal next_seq
            existing = value_to_token.get(value)
            if existing:
                return existing
            token = f"[{kind}_{next_seq}]"
            next_seq += 1
            mapping[token] = value
            value_to_token[value] = token
            return token

        for start, end, kind, value in sorted(spans, key=lambda s: s[0], reverse=True):
            text = text[:start] + token_for(kind, value) + text[end:]

        return text

    def restore(self, text: str, mapping: dict[str, str]) -> str:
        self.validate_mapping(mapping)
        return TOKEN_RE.sub(
            lambda match: mapping.get(match.group(0), match.group(0)),
            text,
        )

    def analyze_spans(
        self,
        text: str,
        filters: Optional[set[str]] = None,
        language: str = "es",
        terms: Optional[Iterable[str]] = None,
    ) -> list[tuple[int, int, str, str]]:
        if not text or not text.strip():
            return []
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {language}")
        active_types = filters if filters is not None else self._all_types(language)
        return self._collect_spans(text, active_types, language, terms)

    def all_types(self, language: str) -> set[str]:
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {language}")
        return self._all_types(language)

    @staticmethod
    def normalize_terms(terms: Optional[Iterable[str]]) -> list[str]:
        """Clean the manual word list: no empty or duplicate entries, capped in size."""
        result: list[str] = []
        used: set[str] = set()
        for term in terms or ():
            cleaned = " ".join(str(term).split())
            key_name = cleaned.casefold()
            if cleaned and len(cleaned) <= MAX_TERM_LENGTH and key_name not in used:
                used.add(key_name)
                result.append(cleaned)
            if len(result) >= MAX_MANUAL_TERMS:
                break
        # Longest terms first: "Ana María" wins over "Ana".
        return sorted(result, key=len, reverse=True)

    @staticmethod
    def validate_mapping(mapping: object) -> None:
        if not isinstance(mapping, dict):
            raise ValueError(tr("err.map_not_object"))
        if len(mapping) > MAX_MAPPING_ENTRIES:
            raise ValueError(tr("err.map_too_big"))
        for token, value in mapping.items():
            if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
                raise ValueError(tr("err.map_bad_token", token=repr(token)))
            if not isinstance(value, str):
                raise ValueError(tr("err.map_bad_value", token=repr(token)))

    def _collect_spans(
        self,
        text: str,
        active_types: set[str],
        language: str,
        terms: Optional[Iterable[str]] = None,
    ) -> list[tuple[int, int, str, str]]:
        # (start, end, type, value, priority). Lower priority wins.
        candidates: list[tuple[int, int, str, str, int]] = []

        for term in self.normalize_terms(terms):
            term_pattern = r"(?<!\w)" + re.escape(term) + r"(?!\w)"
            for match in re.finditer(term_pattern, text, re.IGNORECASE):
                candidates.append(
                    (match.start(), match.end(), "MANUAL", match.group(), -1)
                )

        patterns = {**COMMON_PATTERNS, **PATTERNS_BY_LANGUAGE.get(language, {})}
        for kind, pattern in patterns.items():
            if kind not in active_types:
                continue
            flags = 0 if kind in UPPERCASE_ONLY_TYPES else re.IGNORECASE
            validator = VALIDATORS.get(kind)
            for match in re.finditer(pattern, text, flags):
                value = match.group()
                if validator is not None and not validator(value):
                    continue
                end = match.end()
                if kind == "IBAN":
                    # The pattern is greedy and may swallow the following words.
                    length = _valid_iban_length(value)
                    if length is None:
                        continue
                    value = value[:length]
                    end = match.start() + length
                candidates.append((match.start(), end, kind, value, 0))

        with self._manager.use(language) as nlp:
            for offset, chunk in _split_text(text, MAX_NLP_CHARS):
                doc = nlp(chunk)
                for entity in doc.ents:
                    kind = SPACY_LABELS.get(entity.label_)
                    if kind and kind in active_types:
                        if _is_ner_false_positive(entity.text, language):
                            continue
                        candidates.append(
                            (
                                offset + entity.start_char,
                                offset + entity.end_char,
                                kind,
                                entity.text,
                                10,
                            )
                        )

        return _select_non_overlapping(candidates)

    @staticmethod
    def _next_sequence(text: str, mapping: dict[str, str]) -> int:
        used = [int(m.group(1)) for m in TOKEN_RE.finditer(text)]
        for token in mapping:
            match = TOKEN_RE.fullmatch(token)
            if match:
                used.append(int(match.group(1)))
        return max(used, default=999) + 1

    @staticmethod
    def _all_types(language: str) -> set[str]:
        return (
            set(SPACY_LABELS.values())
            | set(COMMON_PATTERNS)
            | set(PATTERNS_BY_LANGUAGE.get(language, {}))
        )


def _split_text(text: str, max_chars: int) -> Iterable[tuple[int, str]]:
    """Split text while preserving offsets and avoiding cutting words when possible."""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    start = 0
    length = len(text)
    while start < length:
        end = min(start + max_chars, length)
        if end < length:
            minimum = start + max_chars // 2
            break_pos = text.rfind("\n", minimum, end)
            if break_pos < 0:
                break_pos = text.rfind(" ", minimum, end)
            if break_pos >= minimum:
                end = break_pos + 1
        yield start, text[start:end]
        start = end


def _select_non_overlapping(
    candidates: list[tuple[int, int, str, str, int]],
) -> list[tuple[int, int, str, str]]:
    """Prioritize structured patterns and avoid per-character sets."""
    candidates.sort(key=lambda s: (s[4], -(s[1] - s[0]), s[0]))
    intervals: list[tuple[int, int]] = []
    selected_items: list[tuple[int, int, str, str]] = []

    for start, end, kind, value, _priority in candidates:
        pos = bisect_left(intervals, (start, -1))
        overlaps_previous = pos > 0 and intervals[pos - 1][1] > start
        overlaps_next = pos < len(intervals) and intervals[pos][0] < end
        if overlaps_previous or overlaps_next:
            continue
        intervals.insert(pos, (start, end))
        selected_items.append((start, end, kind, value))

    selected_items.sort(key=lambda s: s[0])
    return selected_items


def _valid_iban_length(candidate: str) -> Optional[int]:
    """Return the length of the longest valid IBAN at the start of `candidate`.

    Only cuts at word boundaries (space, hyphen or end), so an IBAN followed by
    text is protected in full without consuming the following words. Returns
    None if there is no valid prefix.
    """
    for end in range(len(candidate), 0, -1):
        if end < len(candidate) and candidate[end] not in " 	-":
            continue
        if candidate[end - 1] in " 	-":
            continue
        if _is_valid_iban(candidate[:end]):
            return end
    return None


def _is_valid_pt_nif(value: str) -> bool:
    """Portuguese NIF: 9 digits, valid first digit and mod 11 check digit."""
    digits = re.sub(r"\D", "", value)
    if len(digits) != 9 or digits[0] not in "1235689":
        return False
    suma = sum(int(d) * (9 - i) for i, d in enumerate(digits[:8]))
    control = 11 - suma % 11
    if control >= 10:
        control = 0
    return control == int(digits[8])


VALIDATORS["NIF_PT"] = _is_valid_pt_nif


def _is_valid_iban(value: str) -> bool:
    normalized = re.sub(r"[\s-]", "", value).upper()
    expected = IBAN_LENGTH_BY_COUNTRY.get(normalized[:2])
    if expected is not None:
        if len(normalized) != expected:
            return False
    elif not 15 <= len(normalized) <= 34:
        return False
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]+", normalized):
        return False
    rearranged = normalized[4:] + normalized[:4]
    numeric = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearranged)
    remainder = 0
    for digit_char in numeric:
        remainder = (remainder * 10 + int(digit_char)) % 97
    return remainder == 1
