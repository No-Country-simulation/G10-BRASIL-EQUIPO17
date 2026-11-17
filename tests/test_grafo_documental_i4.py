"""B-012: grafo LangGraph executavel do I4; fakes/fixtures, sem rede."""
from pathlib import Path

import pytest

pytest.importorskip("langgraph")

from mediflow.agents.grafo_documental import GrafoDocumentalI4, REGRAS
from mediflow.api.triage_service import ServicoTriagem
from mediflow_contracts.models import EntradaProcessada, ExtracaoIA, RecuperacaoRAG
from mediflow.extraction.port import DocumentoParaExtracao
from hashlib import sha256
from mediflow.rules.confirmador_alerta import ConfirmadorAlertaOriginal

RAIZ = Path(__file__).resolve().parents[1]


def extracao(doc: str):
    return ExtracaoIA.model_validate_json((RAIZ / "exemplos" / f"{doc}_extracao_ia.json").read_text("utf-8"))


@pytest.mark.parametrize("doc,conf,regra,formato", [
    ("DOC-001", False, "R005", "pdf"),
    ("DOC-002", True, "R001", "pdf"),
    ("DOC-005", False, "R002", "png"),
])
def test_grafo_tres_cenarios(doc, conf, regra, formato):
    grafo = GrafoDocumentalI4()
    entrada = EntradaProcessada(tipo_entrada=formato, canal_origem="teste_sintetico")
    resultado = grafo.decidir(extracao(doc), entrada=entrada, rag=RecuperacaoRAG(), alerta_textual_confirmado=conf)
    assert resultado.decisao_roteamento.regra_principal == regra
    assert resultado.decisao_roteamento.regras_disparadas[0] == regra
    assert resultado.armazenamento_oci.status == "pendente"


@pytest.mark.parametrize("categoria,esperada", [
    ("solicitacao_exame", "R003"), ("receituario", "R004"),
    ("outro_desconhecido", "R006"),
])
def test_grafo_caminhos_restantes(categoria, esperada):
    extra = extracao("DOC-001") if categoria != "receituario" else extracao("DOC-005")
    extra.tipo_documento = categoria
    if categoria == "solicitacao_exame":
        extra.dados_extraidos.procedimentos = ["Solicitacao ficticia"]
    if categoria == "receituario":
        bruto = extra.model_dump()
        bruto["dados_extraidos"]["medicamentos"][0]["dosagem_status"] = "legivel"
        bruto["dados_extraidos"]["medicamentos"][0]["dosagem_texto"] = "Dose textual sintetica"
        extra = ExtracaoIA.model_validate(bruto)
    saida = GrafoDocumentalI4().decidir(
        extra, entrada=EntradaProcessada(tipo_entrada="pdf", canal_origem="teste"),
        rag=RecuperacaoRAG(), alerta_textual_confirmado=False,
    )
    assert saida.decisao_roteamento.regra_principal == esperada


def test_grafo_r001_vence_r002():
    extra = extracao("DOC-002")
    bruto = extra.model_dump()
    bruto["dados_extraidos"]["paciente"]["nome"] = None
    bruto["dados_extraidos"]["paciente"]["nome_status"] = "ilegivel"
    extra = ExtracaoIA.model_validate(bruto)
    resultado = GrafoDocumentalI4().decidir(
        extra, entrada=EntradaProcessada(tipo_entrada="pdf", canal_origem="teste"),
        rag=RecuperacaoRAG(), alerta_textual_confirmado=True,
    )
    assert resultado.decisao_roteamento.regras_disparadas[:2] == ["R001", "R002"]


def test_grafo_rejeita_alerta_que_nao_e_bool():
    with pytest.raises((TypeError, ValueError)):
        GrafoDocumentalI4().decidir(
            extracao("DOC-002"), entrada=EntradaProcessada(tipo_entrada="pdf", canal_origem="teste"),
            rag=RecuperacaoRAG(), alerta_textual_confirmado=1,
        )


def test_grafo_passa_rag_sem_utilizar_como_alerta():
    rag = RecuperacaoRAG(status="falha", erro_codigo="RAG_ERRO_INTEGRACAO")
    resultado = GrafoDocumentalI4().decidir(
        extracao("DOC-002"), entrada=EntradaProcessada(tipo_entrada="pdf", canal_origem="teste"),
        rag=rag, alerta_textual_confirmado=False,
    )
    assert resultado.rag == rag
    assert resultado.decisao_roteamento.regra_principal != "R001"


def test_grafo_nao_muta_objetos_do_chamador():
    extra = extracao("DOC-001")
    entrada = EntradaProcessada(tipo_entrada="pdf", canal_origem="teste")
    rag = RecuperacaoRAG()
    antes = (extra.model_dump(), entrada.model_dump(), rag.model_dump())
    GrafoDocumentalI4().decidir(extra, entrada=entrada, rag=rag, alerta_textual_confirmado=False)
    assert antes == (extra.model_dump(), entrada.model_dump(), rag.model_dump())


def test_grafo_define_seis_rotas():
    assert REGRAS == ("R001", "R002", "R003", "R004", "R005", "R006")


def test_pipeline_i1_com_grafo_i4_e_original_pdf():
    import pymupdf
    pdf = pymupdf.open()
    pdf.new_page().insert_text((30, 75), "ACHADO CRITICO - URGENTE")
    conteudo = pdf.tobytes()
    pdf.close()
    documento = DocumentoParaExtracao(
        documento_id="DOC-002", arquivo_id="a" * 32, nome_original="amostra.pdf",
        mime_type="application/pdf", conteudo=conteudo, sha256=sha256(conteudo).hexdigest(),
    )

    class ExtratorFixture:
        def extrair(self, _documento):
            return extracao("DOC-002")

    servico = ServicoTriagem(
        extrator=ExtratorFixture(), confirmador=ConfirmadorAlertaOriginal(),
        decisor=GrafoDocumentalI4(),
    )
    resultado = servico.executar(documento, canal_origem="teste")
    assert resultado.decisao_roteamento.regra_principal == "R001"
    assert resultado.armazenamento_oci.status == "pendente"
