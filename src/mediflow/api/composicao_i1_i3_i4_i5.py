"""Composição controlada I1/I3/I4/I5 por arquivo com persistência injetada.

I2 permanece uma porta injetável; não configura Gemini, HTTP ou OCI real.
Uso restrito ao MVP educacional com documentos sintéticos.
"""
from __future__ import annotations

from mediflow.api.composicao_i1_i3_i4 import montar_servico_i1_i3_i4
from mediflow.api.triage_persistence_adapter import (
    ServicoTriagemComOCI,
    montar_servico_triagem_com_oci,
)
from mediflow.api.uploads import ReciboArquivo
from mediflow.extraction.port import ExtratorDocumento
from mediflow.rag.port import RecuperadorReferencias
from mediflow.storage.oci_storage import OCIStorage


def montar_servico_i1_i3_i4_i5(
    *,
    storage: OCIStorage,
    recibo: ReciboArquivo,
    extrator: ExtratorDocumento,
    limite_fontes: int = 3,
    recuperador_referencias: RecuperadorReferencias | None = None,
) -> ServicoTriagemComOCI:
    """Combina os adaptadores reais, sem processar nem gravar na construção.

    Sempre criar uma instância por upload/recibo. O adaptador I5 confere
    documento_id, arquivo_id, hash e canal antes de executar a triagem.
    `storage` pode receber FakeOCI nos testes; jamais criar credenciais aqui.
    """
    base = montar_servico_i1_i3_i4(
        extrator=extrator,
        limite_fontes=limite_fontes,
        recuperador_referencias=recuperador_referencias,
    )
    return montar_servico_triagem_com_oci(
        storage=storage,
        recibo=recibo,
        extrator=base.extrator,
        confirmador=base.confirmador,
        decisor=base.decisor,
        recuperador=base.recuperador,
    )
