"""Preview local da interface com a extração I2 (sem IA real)."""
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import ValidationError
from typing import Annotated, Literal

from mediflow.api.uploads import armazenamento, somente_desenvolvimento_local, _ler_manifesto, MAX_FILE_BYTES
from mediflow.extraction.port import DocumentoParaExtracao, ExtratorDocumento, ExtratorSimulado
from mediflow.storage.oci_storage import OCIStorage
from mediflow_contracts.models import Estrito, ExtracaoIA

router = APIRouter(prefix="/v1/triagens", tags=["integracao-ia"])

MIME_ENTRADA = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpeg": "image/jpeg",
}


class PreviewExtracao(Estrito):
    documento_id: str
    arquivo_id: str
    modo: Literal["simulacao_tecnica"] = "simulacao_tecnica"
    integridade_original: Literal["confirmada"] = "confirmada"
    resultado_contrato: ExtracaoIA
    triagem_executada: Literal[False] = False
    aviso: str = (
        "Simulacao tecnica: campos neutros. Nao houve leitura semantica, "
        "classificacao por IA, diagnostico nem roteamento."
    )


def extrator_de_desenvolvimento() -> ExtratorDocumento:
    """Ponto de substituição em testes; implementação real I2 é tarefa futura."""
    return ExtratorSimulado()


@router.get(
    "/arquivos/{documento_id}/{arquivo_id}/extracao-preview",
    response_model=PreviewExtracao,
    summary="Comprovar integração de bytes OCI ao contrato de extração (SIMULADO)",
)
def previsualizar_integracao_extracao(
    documento_id: Annotated[str, Path(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$")],
    arquivo_id: Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")],
    _: Annotated[None, Depends(somente_desenvolvimento_local)],
    storage: Annotated[OCIStorage, Depends(armazenamento)],
    extrator: Annotated[ExtratorDocumento, Depends(extrator_de_desenvolvimento)],
) -> PreviewExtracao:
    recibo = _ler_manifesto(storage, documento_id, arquivo_id)
    nome = recibo.entrada.nome_arquivo
    sha = recibo.entrada.sha256
    chave = recibo.armazenamento_original.chave_original
    mime = MIME_ENTRADA.get(recibo.entrada.tipo_entrada)
    if not mime or not nome or not sha:
        raise HTTPException(502, detail={
            "codigo": "REGISTRO_INCOMPLETO", "mensagem": "Metadados incompletos para extração."
        })
    try:
        conteudo = storage.download_bytes(chave)
    except Exception as exc:
        raise HTTPException(502, detail={
            "codigo": "ORIGINAL_INDISPONIVEL", "mensagem": "Não foi possível recuperar o arquivo original."
        }) from exc

    if (
        not isinstance(conteudo, bytes)
        or not conteudo
        or len(conteudo) > MAX_FILE_BYTES
        or len(conteudo) != recibo.tamanho_bytes
        or hashlib.sha256(conteudo).hexdigest() != sha
    ):
        raise HTTPException(502, detail={
            "codigo": "INTEGRIDADE_ORIGINAL_INVALIDA",
            "mensagem": "Arquivo original não corresponde aos metadados armazenados."
        })

    documento = DocumentoParaExtracao(
        documento_id=documento_id,
        arquivo_id=arquivo_id,
        nome_original=nome,
        mime_type=mime,
        conteudo=conteudo,
        sha256=sha,
    )
    try:
        resultado_bruto = extrator.extrair(documento)
        resultado = ExtracaoIA.model_validate(resultado_bruto)
    except (ValidationError, ValueError, TypeError) as exc:
        raise HTTPException(502, detail={
            "codigo": "EXTRACAO_CONTRATO_INVALIDO",
            "mensagem": "Módulo de extração retornou dados incompatíveis com o contrato."
        }) from exc
    except Exception as exc:
        raise HTTPException(502, detail={
            "codigo": "EXTRATOR_INDISPONIVEL", "mensagem": "Falha na execução da interface de extração."
        }) from exc

    if resultado.documento_id != documento_id:
        raise HTTPException(502, detail={
            "codigo": "EXTRACAO_DOCUMENTO_DIVERGENTE",
            "mensagem": "O identificador retornado pelo extrator não corresponde ao solicitado."
        })
    return PreviewExtracao(
        documento_id=documento_id,
        arquivo_id=arquivo_id,
        resultado_contrato=resultado,
    )
