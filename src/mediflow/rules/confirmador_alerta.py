"""Confirmação documental independente da LLM para o protótipo MediFlow.

Este verificador lê os bytes originais por OCR/extração de texto, sem
consultar Gemini, RAG ou a saída ExtracaoIA. É deliberadamente conservador:
reconhece somente marcadores EXPRESSOS previstos para amostras sintéticas.
Não substitui triagem clínica nem avaliação de urgência por profissionais.
"""
from __future__ import annotations

import re
import unicodedata
from hashlib import sha256

from mediflow.extraction.pdf_text import extrair_texto_imagem, extrair_texto_pdf
from mediflow.extraction.port import DocumentoParaExtracao

# Frases de alerta literal. 'urgência' isolada não basta: a amostra DOC-001
# contém a expressão negativa 'sem declaração de urgência'.
_MARCADORES_EXPLICITOS = (
    re.compile(r"\bACHADO\s+CRITICO\s*(?:[-:]\s*)?URGENTE\b"),
    re.compile(r"\bALERTA\s+EXPLICITO\s*(?:[-:]\s*)?URGENTE\b"),
    re.compile(r"\bALERTA\s+DE\s+URGENCIA\s*(?:[-:]\s*)?(?:CONFIRMADO|EXPRESSO)\b"),
)


def _normalizar(texto: str) -> str:
    sem_acentos = "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(caractere)
    )
    # PDFs podem usar travessões e hífens tipográficos no marcador.
    sem_acentos = re.sub(r"[\u2010-\u2015\u2212]", "-", sem_acentos)
    return re.sub(r"\s+", " ", sem_acentos.upper()).strip()


class ConfirmadorAlertaOriginal:
    """Implementa ConfirmadorAlerta do I1 sem usar a resposta de IA.

    Uma falha de leitura gera exceção, não uma falsa confirmação negativa.
    A orquestração I1 traduz o erro para CONFIRMACAO_INDISPONIVEL.
    """

    def confirmar(self, documento: DocumentoParaExtracao) -> bool:
        if (
            not isinstance(documento, DocumentoParaExtracao)
            or not isinstance(documento.conteudo, bytes)
            or not documento.conteudo
            or sha256(documento.conteudo).hexdigest() != documento.sha256
        ):
            raise ValueError("Documento original inválido ou com hash divergente.")

        if documento.mime_type == "application/pdf":
            texto = extrair_texto_pdf(documento.conteudo)
        elif documento.mime_type in {"image/png", "image/jpeg"}:
            texto = extrair_texto_imagem(documento.conteudo)
        else:
            raise ValueError("Formato não suportado para confirmação de alerta.")

        if not texto.strip():
            raise ValueError("Não foi possível verificar o conteúdo do original.")
        normalizado = _normalizar(texto)
        for padrao in _MARCADORES_EXPLICITOS:
            for achado in padrao.finditer(normalizado):
                prefixo = normalizado[max(0, achado.start() - 70):achado.start()]
                # Negacao imediatamente anterior ao marcador explicito nao prova alerta.
                segmento = re.split(r"[.!?;]", prefixo)[-1]
                if re.search(r"\b(?:SEM|NAO|NAO HA|AUSENCIA DE)\s+$", segmento):
                    continue
                return True
        return False
