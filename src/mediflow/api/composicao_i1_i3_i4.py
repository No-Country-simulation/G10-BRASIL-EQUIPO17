"""Composição controlada I1 + I3 + I4 para o MVP documental sintético.

Integra implementações reais do RAG I3 e motor/confirmador LangGraph I4,
sem acessar API Gemini, OCI ou publicar rotas HTTP.

O extrator é injetado de propósito: nos testes, usa uma fixture ExtracaoIA;
o adaptador I2 real poderá ser integrado em outro incremento com homologação.
"""
from __future__ import annotations

from mediflow.api.triage_rag_adapter import AdaptadorRAGI3
from mediflow.api.triage_service import ServicoTriagem
from mediflow.extraction.port import ExtratorDocumento
from mediflow.rag.carregador import criar_recuperador_padrao
from mediflow.rag.port import ConsultaRAG, RecuperadorReferencias


def montar_servico_i1_i3_i4(
    *,
    extrator: ExtratorDocumento,
    limite_fontes: int = 3,
    recuperador_referencias: RecuperadorReferencias | None = None,
) -> ServicoTriagem:
    """Monta I1/I3/I4 sem efeitos externos, sem persistidor e sem endpoint.

    `recuperador_referencias` é injetável para testes de indisponibilidade;
    quando omitido, carrega as fichas reais de I3 a partir do pacote.
    """
    if not callable(getattr(extrator, "extrair", None)):
        raise TypeError("Um extrator que implemente extrair(documento) é obrigatório.")

    # Import tardio: integra apenas quando a implementação I4 do PR #33
    # está disponível, sem modificar src/mediflow/rules/ ou o código de I2.
    from mediflow.agents.grafo_documental import GrafoDocumentalI4
    from mediflow.rules.confirmador_alerta import ConfirmadorAlertaOriginal

    recuperador = (
        criar_recuperador_padrao()
        if recuperador_referencias is None
        else recuperador_referencias
    )
    adaptador_rag = AdaptadorRAGI3(
        recuperador=recuperador,
        fabrica_consulta=ConsultaRAG,
        limite=limite_fontes,
    )
    return ServicoTriagem(
        extrator=extrator,
        recuperador=adaptador_rag,
        confirmador=ConfirmadorAlertaOriginal(),
        decisor=GrafoDocumentalI4(),
        persistidor=None,
    )
