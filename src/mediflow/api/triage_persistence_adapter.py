"""Adaptador I1/I5 de persistencia OCI vinculado a um unico upload.

Nao registra rotas, nao consulta credenciais e nao executa Gemini/RAG/LangGraph.
Somente dados sinteticos no MVP educacional; integracao HTTP futura.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePath

from mediflow.api.triage_service import (
    ConfirmadorAlerta,
    DecisorTriagem,
    ProvedorRAG,
    ServicoTriagem,
)
from mediflow.api.uploads import ReciboArquivo
from mediflow.extraction.port import DocumentoParaExtracao, ExtratorDocumento
from mediflow.storage.oci_storage import OCIStorage
from mediflow.storage.triage_persistence import persistir_resultado
from mediflow_contracts.models import ResultadoTriagem

_MIME = {"pdf": "application/pdf", "png": "image/png", "jpeg": "image/jpeg"}
_EXTENSOES = {"pdf": {".pdf"}, "png": {".png"}, "jpeg": {".jpg", ".jpeg"}}


class VinculoArquivoInvalido(ValueError):
    """O original e o manifesto nao pertencem a mesma execucao."""


def _validar_recibo(storage: OCIStorage, recibo: ReciboArquivo) -> None:
    if not isinstance(storage, OCIStorage) or not isinstance(recibo, ReciboArquivo):
        raise TypeError("Armazenamento e recibo validado sao obrigatorios.")

    tipo = recibo.entrada.tipo_entrada
    nome = recibo.entrada.nome_arquivo
    if not nome or not recibo.entrada.sha256 or tipo not in _EXTENSOES:
        raise VinculoArquivoInvalido("Manifesto incompleto para persistencia.")
    normalizado = nome.replace("\\", "/")
    extensao = PurePath(normalizado).suffix.lower()
    doc, arq = recibo.documento_id, recibo.arquivo_id
    if (
        storage.bucket != recibo.armazenamento_original.bucket
        or PurePath(normalizado).name != nome
        or extensao not in _EXTENSOES[tipo]
        or recibo.armazenamento_original.chave_original != f"originais/{doc}/{arq}{extensao}"
        or recibo.registro_metadados.chave_metadados != f"metadados/{doc}/{arq}.json"
    ):
        raise VinculoArquivoInvalido("Manifesto possui referencias OCI inconsistentes.")


def _validar_documento_da_execucao(
    recibo: ReciboArquivo, documento: DocumentoParaExtracao, canal_origem: str
) -> None:
    """Impede que um persistidor por requisicao seja reutilizado para outro arquivo."""
    if not isinstance(documento, DocumentoParaExtracao):
        raise VinculoArquivoInvalido("Documento invalido para a execucao.")
    entrada = recibo.entrada
    if (
        documento.documento_id != recibo.documento_id
        or documento.arquivo_id != recibo.arquivo_id
        or documento.nome_original != entrada.nome_arquivo
        or documento.mime_type != _MIME.get(entrada.tipo_entrada)
        or documento.sha256 != entrada.sha256
        or not isinstance(documento.conteudo, bytes)
        or len(documento.conteudo) != recibo.tamanho_bytes
        or sha256(documento.conteudo).hexdigest() != entrada.sha256
        or canal_origem != entrada.canal_origem
    ):
        raise VinculoArquivoInvalido("Documento nao corresponde ao recibo da execucao.")


@dataclass(frozen=True, slots=True)
class PersistidorResultadoOCI:
    """Implementa PersistidorTriagem e delega a escrita ao modulo I5."""

    storage: OCIStorage
    recibo: ReciboArquivo

    def __post_init__(self) -> None:
        _validar_recibo(self.storage, self.recibo)
        # Snapshot defensivo: modificacoes no recibo do chamador nao afetam este vinculo.
        object.__setattr__(self, "recibo", self.recibo.model_copy(deep=True))

    def persistir(self, resultado: ResultadoTriagem) -> ResultadoTriagem:
        """Nenhuma escrita na construcao; somente ao executar o pipeline."""
        return persistir_resultado(self.storage, self.recibo, resultado)


@dataclass(frozen=True, slots=True)
class ServicoTriagemComOCI:
    """Fachada por requisicao que amarra o arquivo_id antes de executar o I1."""

    _servico: ServicoTriagem
    _recibo: ReciboArquivo

    def executar(
        self, documento: DocumentoParaExtracao, *, canal_origem: str
    ) -> ResultadoTriagem:
        _validar_documento_da_execucao(self._recibo, documento, canal_origem)
        return self._servico.executar(documento, canal_origem=canal_origem)


def montar_servico_triagem_com_oci(
    *,
    storage: OCIStorage,
    recibo: ReciboArquivo,
    extrator: ExtratorDocumento,
    confirmador: ConfirmadorAlerta,
    decisor: DecisorTriagem,
    recuperador: ProvedorRAG | None = None,
) -> ServicoTriagemComOCI:
    """Composicao por documento, nao reutilizar globalmente entre requisicoes.

    O chamador deve obter recibo de _ler_manifesto autenticado e validar original.
    Aqui nao sao montados adaptadores reais de I2/I3/I4; devem ser injetados.
    """
    persistidor = PersistidorResultadoOCI(storage=storage, recibo=recibo)
    servico = ServicoTriagem(
        extrator=extrator,
        confirmador=confirmador,
        decisor=decisor,
        recuperador=recuperador,
        persistidor=persistidor,
    )
    return ServicoTriagemComOCI(servico, persistidor.recibo.model_copy(deep=True))
