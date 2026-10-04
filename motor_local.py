"""Motor local de protección reversible de CloakText.

Todo el procesamiento se realiza en el equipo. El motor mantiene como máximo
un modelo spaCy cargado, procesa textos extensos por bloques y prioriza
identificadores estructurados (email, IBAN, teléfono...) frente a entidades NER
cuando ambos detectores se solapan.
"""

from __future__ import annotations

import gc
from bisect import bisect_left
import logging
import re
import threading
import time
from typing import Iterable, Optional

import spacy

from language_models import (
    IDIOMAS_SOPORTADOS,
    MODELOS_SPACY,
    instalar_modelo as instalar_paquete_idioma,
    modelo_disponible as paquete_idioma_disponible,
    ruta_modelo_local,
)

logger = logging.getLogger(__name__)

MAX_NLP_CHARS = 200_000
MAX_MAPA_ENTRADAS = 100_000
TOKEN_RE = re.compile(r"\[[A-Z][A-Z0-9_]*_(\d+)\]")

PATRONES_COMUNES = {
    "EMAIL": r"\b[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+\b",
    "IBAN": r"\b[A-Z]{2}\d{2}(?:[\s-]?[A-Z0-9]){11,30}\b",
    "IP": r"\b(?:(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\b",
}

PATRONES_POR_IDIOMA = {
    "es": {
        "NIF": r"\b\d{8}[A-HJ-NP-TV-Z]\b",
        "NIE": r"\b[XYZ]\d{7}[A-Z]\b",
        "TELEFONO": r"(?<!\d)(?:\+34[\s\-]?)?[6789]\d{2}[\s\-]?\d{3}[\s\-]?\d{3}(?!\d)",
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
        "TELEFONO": r"(?<!\d)(?:\+34[\s\-]?)?[6789]\d{2}[\s\-]?\d{3}[\s\-]?\d{3}(?!\d)",
        "FECHA_NAC": r"\b(?:0?[1-9]|[12]\d|3[01])[/\-.](?:0?[1-9]|1[0-2])[/\-.](?:19|20)\d{2}\b",
    },
}

ETIQUETAS_SPACY = {"PER": "PERSONA", "PERSON": "PERSONA", "LOC": "LUGAR", "GPE": "LUGAR", "ORG": "ORG"}

FALSOS_POSITIVOS_NER_POR_IDIOMA = {
    "es": {"hola", "gracias", "adiós", "buenos días", "buenas tardes", "buenas noches"},
    "en": {"hello", "hi", "thanks", "thank you", "goodbye"},
    "fr": {"bonjour", "salut", "merci", "au revoir"},
    "de": {"hallo", "danke", "tschüss", "guten morgen", "guten tag", "guten abend"},
    "it": {"ciao", "grazie", "buongiorno", "buonasera"},
    "pt": {"olá", "oi", "obrigado", "obrigada", "bom dia", "boa tarde", "boa noite"},
    "ca": {"hola", "gràcies", "adéu", "bon dia", "bona tarda", "bona nit"},
}


def _es_falso_positivo_ner(valor: str, idioma: str) -> bool:
    normalizado = " ".join(valor.casefold().strip().strip(".,;:!?¡¿").split())
    return normalizado in FALSOS_POSITIVOS_NER_POR_IDIOMA.get(idioma, set())


class ModeloNoDisponibleError(ValueError):
    def __init__(self, idioma: str, modelo: str):
        self.idioma = idioma
        self.modelo = modelo
        super().__init__(f"El modelo de idioma '{modelo}' no está disponible.")


class GestorModeloUnico:
    """Mantiene como máximo un modelo spaCy cargado en memoria."""

    def __init__(self, ttl_minutos: int = 20):
        self._nlp: Optional[spacy.language.Language] = None
        self._idioma: Optional[str] = None
        self._ultimo_uso = 0.0
        self._en_uso = 0
        self._lock = threading.Condition()
        self._ttl = max(1, ttl_minutos) * 60
        self._parar = False
        self._hilo = threading.Thread(target=self._limpiar_loop, daemon=True, name="cloaktext-model-ttl")
        self._hilo.start()

    def idioma_cargado(self) -> Optional[str]:
        with self._lock:
            return self._idioma

    def usar(self, idioma: str):
        return _UsoModelo(self, idioma)

    def descargar(self) -> bool:
        """Libera el modelo si no está procesando. Devuelve True si quedó libre."""
        with self._lock:
            if self._en_uso:
                return False
            self._descargar_interno()
            return True

    def detener(self) -> None:
        with self._lock:
            self._parar = True
            if self._en_uso == 0:
                self._descargar_interno()
            self._lock.notify_all()

    def _adquirir(self, idioma: str):
        if idioma not in IDIOMAS_SOPORTADOS:
            raise ValueError(f"Idioma no soportado: {idioma}")

        with self._lock:
            while self._idioma is not None and self._idioma != idioma and self._en_uso > 0:
                self._lock.wait()

            if self._idioma != idioma:
                self._descargar_interno()
                self._cargar(idioma)

            self._ultimo_uso = time.monotonic()
            self._en_uso += 1
            return self._nlp

    def _liberar(self) -> None:
        with self._lock:
            self._en_uso = max(0, self._en_uso - 1)
            self._ultimo_uso = time.monotonic()
            self._lock.notify_all()

    def _cargar(self, idioma: str) -> None:
        nombre = MODELOS_SPACY[idioma]
        logger.info("Cargando modelo spaCy: %s", nombre)
        try:
            self._nlp = spacy.load(nombre)
        except OSError:
            ruta = ruta_modelo_local(idioma)
            if ruta is None:
                raise ModeloNoDisponibleError(idioma, nombre)
            self._nlp = spacy.load(ruta)

        self._idioma = idioma
        self._ultimo_uso = time.monotonic()
        logger.info("Modelo listo: %s", nombre)

    def _descargar_interno(self) -> None:
        anterior = self._nlp
        if anterior is not None:
            logger.info("Liberando modelo de memoria: %s", MODELOS_SPACY.get(self._idioma))
        self._nlp = None
        self._idioma = None
        if anterior is not None:
            del anterior
            gc.collect()

    def _limpiar_loop(self) -> None:
        while True:
            with self._lock:
                if self._parar:
                    return
                self._lock.wait(timeout=30)
                if self._parar:
                    return
                if (
                    self._idioma is not None
                    and self._en_uso == 0
                    and time.monotonic() - self._ultimo_uso > self._ttl
                ):
                    self._descargar_interno()


class _UsoModelo:
    def __init__(self, gestor: GestorModeloUnico, idioma: str):
        self._gestor = gestor
        self._idioma = idioma

    def __enter__(self) -> spacy.language.Language:
        return self._gestor._adquirir(self._idioma)

    def __exit__(self, exc_type, exc, tb):
        self._gestor._liberar()
        return False


class MotorLocal:
    def __init__(self, ttl_minutos: int = 20):
        self._gestor = GestorModeloUnico(ttl_minutos=ttl_minutos)

    def idioma_cargado(self) -> Optional[str]:
        return self._gestor.idioma_cargado()

    def descargar_modelo(self) -> bool:
        return self._gestor.descargar()

    @staticmethod
    def modelo_disponible(idioma: str) -> bool:
        return paquete_idioma_disponible(idioma)

    @staticmethod
    def instalar_modelo(idioma: str, progreso=None):
        return instalar_paquete_idioma(idioma, progreso)

    def detener(self) -> None:
        self._gestor.detener()

    def anonimizar(
        self,
        texto: str,
        mapa: dict[str, str],
        filtros: Optional[set[str]] = None,
        idioma: str = "es",
    ) -> str:
        if not texto or not texto.strip():
            return texto
        if idioma not in IDIOMAS_SOPORTADOS:
            raise ValueError(f"Idioma no soportado: {idioma}")

        self.validar_mapa(mapa)
        activos = filtros if filtros is not None else self._todos_tipos(idioma)
        spans = self._recoger_spans(texto, activos, idioma)
        siguiente = self._siguiente_secuencia(texto, mapa)

        valor_a_token = {valor: token for token, valor in mapa.items()}

        def token_para(tipo: str, valor: str) -> str:
            nonlocal siguiente
            existente = valor_a_token.get(valor)
            if existente:
                return existente
            token = f"[{tipo}_{siguiente}]"
            siguiente += 1
            mapa[token] = valor
            valor_a_token[valor] = token
            return token

        for inicio, fin, tipo, valor in sorted(spans, key=lambda s: s[0], reverse=True):
            texto = texto[:inicio] + token_para(tipo, valor) + texto[fin:]

        return texto

    def desanonimizar(self, texto: str, mapa: dict[str, str]) -> str:
        self.validar_mapa(mapa)
        return TOKEN_RE.sub(
            lambda coincidencia: mapa.get(coincidencia.group(0), coincidencia.group(0)),
            texto,
        )

    def analizar_spans(
        self,
        texto: str,
        filtros: Optional[set[str]] = None,
        idioma: str = "es",
    ) -> list[tuple[int, int, str, str]]:
        if not texto or not texto.strip():
            return []
        if idioma not in IDIOMAS_SOPORTADOS:
            raise ValueError(f"Idioma no soportado: {idioma}")
        activos = filtros if filtros is not None else self._todos_tipos(idioma)
        return self._recoger_spans(texto, activos, idioma)

    def todos_tipos(self, idioma: str) -> set[str]:
        if idioma not in IDIOMAS_SOPORTADOS:
            raise ValueError(f"Idioma no soportado: {idioma}")
        return self._todos_tipos(idioma)

    @staticmethod
    def validar_mapa(mapa: object) -> None:
        if not isinstance(mapa, dict):
            raise ValueError("El diccionario debe ser un objeto JSON.")
        if len(mapa) > MAX_MAPA_ENTRADAS:
            raise ValueError("El diccionario es demasiado grande.")
        for token, valor in mapa.items():
            if not isinstance(token, str) or not TOKEN_RE.fullmatch(token):
                raise ValueError(f"Token de diccionario no válido: {token!r}")
            if not isinstance(valor, str):
                raise ValueError(f"El valor de {token!r} debe ser texto.")

    def _recoger_spans(
        self,
        texto: str,
        activos: set[str],
        idioma: str,
    ) -> list[tuple[int, int, str, str]]:
        # (inicio, fin, tipo, valor, prioridad). Menor prioridad gana.
        candidatos: list[tuple[int, int, str, str, int]] = []

        patrones = {**PATRONES_COMUNES, **PATRONES_POR_IDIOMA.get(idioma, {})}
        for tipo, patron in patrones.items():
            if tipo not in activos:
                continue
            for coincidencia in re.finditer(patron, texto, re.IGNORECASE):
                valor = coincidencia.group()
                if tipo == "IBAN" and not _iban_valido(valor):
                    continue
                candidatos.append(
                    (coincidencia.start(), coincidencia.end(), tipo, valor, 0)
                )

        with self._gestor.usar(idioma) as nlp:
            for offset, bloque in _trocear_texto(texto, MAX_NLP_CHARS):
                doc = nlp(bloque)
                for entidad in doc.ents:
                    tipo = ETIQUETAS_SPACY.get(entidad.label_)
                    if tipo and tipo in activos:
                        if _es_falso_positivo_ner(entidad.text, idioma):
                            continue
                        candidatos.append(
                            (
                                offset + entidad.start_char,
                                offset + entidad.end_char,
                                tipo,
                                entidad.text,
                                10,
                            )
                        )

        return _seleccionar_no_solapados(candidatos)

    @staticmethod
    def _siguiente_secuencia(texto: str, mapa: dict[str, str]) -> int:
        usados = [int(m.group(1)) for m in TOKEN_RE.finditer(texto)]
        for token in mapa:
            coincidencia = TOKEN_RE.fullmatch(token)
            if coincidencia:
                usados.append(int(coincidencia.group(1)))
        return max(usados, default=999) + 1

    @staticmethod
    def _todos_tipos(idioma: str) -> set[str]:
        return (
            set(ETIQUETAS_SPACY.values())
            | set(PATRONES_COMUNES)
            | set(PATRONES_POR_IDIOMA.get(idioma, {}))
        )


def _trocear_texto(texto: str, max_chars: int) -> Iterable[tuple[int, str]]:
    """Divide texto preservando offsets y evitando cortar palabras si es posible."""
    if max_chars <= 0:
        raise ValueError("max_chars debe ser positivo")
    inicio = 0
    longitud = len(texto)
    while inicio < longitud:
        fin = min(inicio + max_chars, longitud)
        if fin < longitud:
            minimo = inicio + max_chars // 2
            salto = texto.rfind("\n", minimo, fin)
            if salto < 0:
                salto = texto.rfind(" ", minimo, fin)
            if salto >= minimo:
                fin = salto + 1
        yield inicio, texto[inicio:fin]
        inicio = fin


def _seleccionar_no_solapados(
    candidatos: list[tuple[int, int, str, str, int]],
) -> list[tuple[int, int, str, str]]:
    """Prioriza patrones estructurados y evita conjuntos por carácter."""
    candidatos.sort(key=lambda s: (s[4], -(s[1] - s[0]), s[0]))
    intervalos: list[tuple[int, int]] = []
    seleccionados: list[tuple[int, int, str, str]] = []

    for inicio, fin, tipo, valor, _prioridad in candidatos:
        pos = bisect_left(intervalos, (inicio, -1))
        solapa_anterior = pos > 0 and intervalos[pos - 1][1] > inicio
        solapa_siguiente = pos < len(intervalos) and intervalos[pos][0] < fin
        if solapa_anterior or solapa_siguiente:
            continue
        intervalos.insert(pos, (inicio, fin))
        seleccionados.append((inicio, fin, tipo, valor))

    seleccionados.sort(key=lambda s: s[0])
    return seleccionados


def _iban_valido(valor: str) -> bool:
    normalizado = re.sub(r"[\s-]", "", valor).upper()
    if not 15 <= len(normalizado) <= 34:
        return False
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]+", normalizado):
        return False
    reorganizado = normalizado[4:] + normalizado[:4]
    numerico = "".join(str(ord(c) - 55) if c.isalpha() else c for c in reorganizado)
    resto = 0
    for caracter in numerico:
        resto = (resto * 10 + int(caracter)) % 97
    return resto == 1
