"""Orquestração I1 independente de HTTP, OCI, Gemini e LangGraph.

Incremento preparatório do MVP, exclusivo para documentos sintéticos.
O I1 coordena interfaces; a decisão pertence ao I4, o RAG ao I3,
a extração ao I2 e a persistência ao I5. Não expõe endpoint.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Protocol

from mediflow.extraction.port import DocumentoParaExtracao, ExtratorDocumento
from mediflow_contracts.models import (
    EntradaProcessada,
    ExtracaoIA,
    RecuperacaoRAG,
    ResultadoTriagem,
)

_TIPOS = {
    "application/pdf": "pdf",
    "image/png": "png",
    "image/jpeg": "jpeg",
}
_DOCUMENTO_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{2,63}$")
_ARQUIVO_ID = re.compile(r"^[a-f0-9]{32}$")


class ConfirmadorAlerta(Protocol):
    """I4: confirmação determinística no ORIGINAL, nunca na saída da LLM."""

    def confirmar(self, documento: DocumentoParaExtracao) -> bool: ...


class ProvedorRAG(Protocol):
    """Adaptador futuro I3: converte a extração em consulta e fontes versionadas."""

    def buscar(self, extracao: ExtracaoIA) -> RecuperacaoRAG: ...


class DecisorTriagem(Protocol):
    """I4: decide pela precedência R001–R006; I1 não reimplementa regras."""

    def decidir(
        self,
        extracao: ExtracaoIA,
        *,
        entrada: EntradaProcessada,
        rag: RecuperacaoRAG,
        alerta_textual_confirmado: bool,
    ) -> ResultadoTriagem: ...


class PersistidorTriagem(Protocol):
    """Adaptador I5 com recibo/OCI associados fora deste serviço."""

    def persistir(self, resultado: ResultadoTriagem) -> ResultadoTriagem: ...


class FalhaOrquestracao(RuntimeError):
    """Erro público sem dados de documento, credenciais ou exceção remota."""

    def __init__(self, codigo: str, etapa: str) -> None:
        self.codigo = codigo
        self.etapa = etapa
        super().__init__(f"Falha na etapa {etapa}: {codigo}")


def _validar_documento(documento: DocumentoParaExtracao, canal_origem: str) -> EntradaProcessada:
    if not isinstance(documento, DocumentoParaExtracao):
        raise FalhaOrquestracao("DOCUMENTO_INVALIDO", "entrada")
    if (
        not _DOCUMENTO_ID.fullmatch(documento.documento_id)
        or not _ARQUIVO_ID.fullmatch(documento.arquivo_id)
        or not isinstance(documento.conteudo, bytes)
        or not documento.conteudo
        or not isinstance(documento.nome_original, str)
        or not documento.nome_original.strip()
        or documento.mime_type not in _TIPOS
        or not isinstance(canal_origem, str)
        or not (1 <= len(canal_origem.strip()) <= 80)
        or hashlib.sha256(documento.conteudo).hexdigest() != documento.sha256
    ):
        raise FalhaOrquestracao("DOCUMENTO_INVALIDO", "entrada")
    return EntradaProcessada(
        tipo_entrada=_TIPOS[documento.mime_type],
        canal_origem=canal_origem,
        sha256=documento.sha256,
        nome_arquivo=documento.nome_original,
    )


def _sem_dados_de_storage(resultado: ResultadoTriagem) -> dict:
    dados = resultado.model_dump(mode="json")
    dados.pop("armazenamento_oci", None)
    return dados


@dataclass(frozen=True, slots=True)
class ServicoTriagem:
    extrator: ExtratorDocumento
    confirmador: ConfirmadorAlerta
    decisor: DecisorTriagem
    recuperador: ProvedorRAG | None = None
    persistidor: PersistidorTriagem | None = None

    def executar(
        self, documento: DocumentoParaExtracao, *, canal_origem: str
    ) -> ResultadoTriagem:
        """Executa o pipeline por contratos, sem afirmar integração real no teste.

        Sem persistidor, devolve somente ResultadoTriagem com armazenamento
        PENDENTE. Erro na confirmação de urgência ou decisão interrompe o fluxo.
        A falha opcional de RAG é registrada e não se converte em decisão.
        """
        entrada = _validar_documento(documento, canal_origem)

        try:
            extracao = ExtracaoIA.model_validate(self.extrator.extrair(documento))
        except Exception as exc:
            raise FalhaOrquestracao("EXTRACAO_INVALIDA_OU_INDISPONIVEL", "extracao") from exc
        if extracao.documento_id != documento.documento_id:
            raise FalhaOrquestracao("DOCUMENTO_DIVERGENTE", "extracao")
        # Referência canônica imutável por isolamento defensivo: nenhum adaptador
        # pode alterar a extração original via objetos Pydantic compartilhados.
        extracao_base = extracao.model_copy(deep=True)

        # A verificação não recebe ExtracaoIA para evitar confirmar a própria LLM.
        try:
            alerta_confirmado = self.confirmador.confirmar(documento)
        except Exception as exc:
            raise FalhaOrquestracao("CONFIRMACAO_INDISPONIVEL", "alerta") from exc
        if type(alerta_confirmado) is not bool:
            raise FalhaOrquestracao("CONFIRMACAO_INVALIDA", "alerta")

        rag = RecuperacaoRAG(status="nao_consultado")
        if self.recuperador is not None:
            try:
                rag = RecuperacaoRAG.model_validate(self.recuperador.buscar(extracao_base.model_copy(deep=True)))
            except Exception:
                # RAG não decide nem rebaixa a prioridade; falha é registrada.
                rag = RecuperacaoRAG(status="falha", erro_codigo="RAG_ERRO_INTEGRACAO")

        try:
            resultado = ResultadoTriagem.model_validate(
                self.decisor.decidir(
                    extracao_base.model_copy(deep=True),
                    entrada=entrada.model_copy(deep=True),
                    rag=rag.model_copy(deep=True),
                    alerta_textual_confirmado=alerta_confirmado,
                )
            )
        except Exception as exc:
            raise FalhaOrquestracao("DECISAO_INVALIDA_OU_INDISPONIVEL", "decisao") from exc

        if (
            resultado.documento_id != documento.documento_id
            or resultado.entrada != entrada
            or resultado.rag != rag
            or resultado.dados_extraidos != extracao_base.dados_extraidos
            or resultado.evidencias != extracao_base.evidencias
            or resultado.classificacao.tipo_documento != extracao_base.tipo_documento
            or resultado.classificacao.especialidade_texto != extracao_base.especialidade_texto
            or resultado.status not in {"processado", "aguardando_auditoria"}
            or resultado.armazenamento_oci.status != "pendente"
        ):
            raise FalhaOrquestracao("RESULTADO_INCONSISTENTE", "decisao")

        regra = resultado.decisao_roteamento.regra_principal
        disparadas = resultado.decisao_roteamento.regras_disparadas
        if (
            (alerta_confirmado and regra != "R001")
            or (not alerta_confirmado and (regra == "R001" or "R001" in disparadas))
        ):
            raise FalhaOrquestracao("ALERTA_SEM_CONFIRMACAO_INDEPENDENTE", "decisao")
        if regra not in disparadas:
            raise FalhaOrquestracao("RESULTADO_INCONSISTENTE", "decisao")

        # O I4 e fonte de verdade: validar os metadados com o catalogo canonico.
        try:
            from mediflow.rules.motor_deterministico import validar_metadados_resultado

            consistente = validar_metadados_resultado(resultado)
        except Exception as exc:
            raise FalhaOrquestracao("RESULTADO_INCONSISTENTE", "decisao") from exc
        if not consistente:
            raise FalhaOrquestracao("RESULTADO_INCONSISTENTE", "decisao")

        if self.persistidor is None:
            return resultado

        try:
            armazenado = ResultadoTriagem.model_validate(
                self.persistidor.persistir(resultado.model_copy(deep=True))
            )
        except Exception as exc:
            raise FalhaOrquestracao("PERSISTENCIA_INDISPONIVEL", "persistencia") from exc

        if (
            armazenado.armazenamento_oci.status != "confirmado"
            or _sem_dados_de_storage(armazenado) != _sem_dados_de_storage(resultado)
        ):
            raise FalhaOrquestracao("PERSISTENCIA_NAO_CONFIRMADA", "persistencia")
        return armazenado
