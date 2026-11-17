"""Integração de contrato I1/I3/I5 com fakes e documentos sintéticos.

Não chama OCI real, Gemini, RAG definitivo ou LangGraph.
Reutiliza as fábricas já exercitadas pelos testes isolados dos adaptadores.
"""

from __future__ import annotations

import pytest

from mediflow.api.triage_persistence_adapter import montar_servico_triagem_com_oci
from mediflow.api.triage_rag_adapter import AdaptadorRAGI3
from mediflow.api.triage_service import FalhaOrquestracao
from mediflow_contracts.models import FonteRAG, RecuperacaoRAG, ResultadoTriagem
from test_triage_persistence_adapter import (
    ConfirmadorPorBytesDeTeste,
    DecisorDeFixture,
    ExtratorDeFixture,
    preparar,
)
from test_triage_rag_adapter import ConsultaDeTeste, RecuperadorFake


def recuperador_sintetico(fonte_id: str = "FONTE-SINTETICA") -> RecuperadorFake:
    return RecuperadorFake(
        RecuperacaoRAG(
            status="consultado",
            fontes=[
                FonteRAG(
                    fonte_id=fonte_id,
                    titulo="Referência fictícia para testes",
                    versao="0.1",
                )
            ],
        )
    )


def montar(storage, recibo, recuperador):
    """Composição real dos adaptadores, com I2/I4 substituídos por fixtures."""
    return montar_servico_triagem_com_oci(
        storage=storage,
        recibo=recibo,
        extrator=ExtratorDeFixture(),
        confirmador=ConfirmadorPorBytesDeTeste(),
        decisor=DecisorDeFixture(),
        recuperador=AdaptadorRAGI3(
            recuperador=recuperador,
            fabrica_consulta=ConsultaDeTeste,
            limite=3,
        ),
    )


@pytest.mark.parametrize(
    "doc_id,regra,status_esperado",
    [
        ("DOC-001", "R005", "processado"),
        ("DOC-002", "R001", "aguardando_auditoria"),
        ("DOC-005", "R002", "aguardando_auditoria"),
    ],
)
def test_tres_cenarios_rag_e_oci_na_mesma_execucao(doc_id, regra, status_esperado):
    fake_oci, storage, recibo, documento = preparar(doc_id)
    entrada_intocada = dict(fake_oci.objetos)
    recuperador = recuperador_sintetico()
    servico = montar(storage, recibo, recuperador)

    # Construir serviços e adaptadores não deve gravar nada.
    assert fake_oci.gravacoes == []
    resultado = servico.executar(documento, canal_origem=recibo.entrada.canal_origem)

    assert resultado.documento_id == doc_id
    assert resultado.status == status_esperado
    assert resultado.decisao_roteamento.regra_principal == regra
    assert resultado.rag.status == "consultado"
    assert resultado.rag.fontes[0].fonte_id == "FONTE-SINTETICA"
    assert resultado.armazenamento_oci.status == "confirmado"
    assert len(recuperador.consultas) == 1
    assert recuperador.consultas[0].limite == 3
    assert documento.documento_id not in recuperador.consultas[0].texto

    # Persistência OCI simulada contém o RAG e a decisão da MESMA execução.
    assert len(fake_oci.gravacoes) == 2
    chave_historico, chave_resultado = fake_oci.gravacoes
    assert chave_historico.startswith(f"historicos/{doc_id}/{documento.arquivo_id}/")
    assert chave_resultado.startswith(f"resultados/{doc_id}/{documento.arquivo_id}/")
    assert resultado.armazenamento_oci.chave_historico == chave_historico
    assert resultado.armazenamento_oci.chave_resultado == chave_resultado
    persistido = ResultadoTriagem.model_validate_json(fake_oci.objetos[chave_resultado])
    assert persistido == resultado
    assert persistido.rag.fontes[0].fonte_id == "FONTE-SINTETICA"
    assert all(fake_oci.objetos[chave] == dados for chave, dados in entrada_intocada.items())


def test_falha_do_rag_nao_impede_persistencia_da_decisao():
    class RecuperadorIndisponivel:
        def buscar(self, consulta):
            raise RuntimeError("SEGREDO_RAG_FICTICIO")

    fake_oci, storage, recibo, documento = preparar("DOC-001")
    resultado = montar(storage, recibo, RecuperadorIndisponivel()).executar(
        documento, canal_origem=recibo.entrada.canal_origem
    )
    assert resultado.rag.status == "falha"
    assert resultado.rag.erro_codigo == "RAG_ERRO_INTEGRACAO"
    assert resultado.decisao_roteamento.regra_principal == "R005"
    assert resultado.armazenamento_oci.status == "confirmado"
    gravado = ResultadoTriagem.model_validate_json(
        fake_oci.objetos[resultado.armazenamento_oci.chave_resultado]
    )
    assert gravado == resultado
    assert "SEGREDO_RAG_FICTICIO" not in str(gravado.model_dump())


def test_falha_oci_apos_rag_nao_declara_sucesso():
    fake_oci, storage, recibo, documento = preparar("DOC-001")
    fake_oci.falhar_prefixo = "resultados/"
    recuperador = recuperador_sintetico()

    with pytest.raises(FalhaOrquestracao) as erro:
        montar(storage, recibo, recuperador).executar(
            documento, canal_origem=recibo.entrada.canal_origem
        )

    assert erro.value.codigo == "PERSISTENCIA_INDISPONIVEL"
    assert len(recuperador.consultas) == 1
    assert len(fake_oci.gravacoes) == 1
    assert fake_oci.gravacoes[0].startswith("historicos/")
    assert not any(chave.startswith("resultados/") for chave in fake_oci.objetos)
    assert "SEGREDO_OCI_SIMULADO" not in str(erro.value)


def test_contextos_e_fontes_nao_se_misturam_entre_documentos():
    fake_oci, storage, recibo_a, documento_a = preparar("DOC-001", arquivo_id="a" * 32)
    outro_fake, _, recibo_b, documento_b = preparar("DOC-005", arquivo_id="b" * 32)
    fake_oci.objetos.update(outro_fake.objetos)  # Mesmo bucket simulado, dois uploads.

    rag_a = recuperador_sintetico("FONTE-DO-001")
    rag_b = recuperador_sintetico("FONTE-DO-005")
    resultado_a = montar(storage, recibo_a, rag_a).executar(
        documento_a, canal_origem=recibo_a.entrada.canal_origem
    )
    resultado_b = montar(storage, recibo_b, rag_b).executar(
        documento_b, canal_origem=recibo_b.entrada.canal_origem
    )

    assert resultado_a.rag.fontes[0].fonte_id == "FONTE-DO-001"
    assert resultado_b.rag.fontes[0].fonte_id == "FONTE-DO-005"
    assert resultado_a.decisao_roteamento.regra_principal == "R005"
    assert resultado_b.decisao_roteamento.regra_principal == "R002"
    assert resultado_a.armazenamento_oci.chave_resultado != resultado_b.armazenamento_oci.chave_resultado
    assert resultado_a.armazenamento_oci.chave_historico != resultado_b.armazenamento_oci.chave_historico
    assert len(rag_a.consultas) == len(rag_b.consultas) == 1
    assert len(fake_oci.gravacoes) == 4
    assert ResultadoTriagem.model_validate_json(
        fake_oci.objetos[resultado_a.armazenamento_oci.chave_resultado]
    ) == resultado_a
    assert ResultadoTriagem.model_validate_json(
        fake_oci.objetos[resultado_b.armazenamento_oci.chave_resultado]
    ) == resultado_b
