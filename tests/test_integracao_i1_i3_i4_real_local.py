"""Integração verdadeira do recuperador I3 e do LangGraph/confirmador I4.

O contrato de extração é fornecido por exemplos sintéticos do repositório;
não chama Gemini, OCI nem HTTP e não substitui a homologação do I2.
"""
from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from mediflow.api.composicao_i1_i3_i4 import montar_servico_i1_i3_i4
from mediflow.api.triage_service import FalhaOrquestracao
from mediflow.extraction.port import DocumentoParaExtracao
from mediflow_contracts.models import ExtracaoIA, RecuperacaoRAG, SinaisDocumentais

RAIZ = Path(__file__).resolve().parents[1]
ORIGINAIS = {
    "DOC-001": ("amostras/pdf/DOC-001_laudo_laboratorial_rotina.pdf", "application/pdf"),
    "DOC-002": ("amostras/pdf/DOC-002_laudo_imagem_alerta.pdf", "application/pdf"),
    "DOC-005": ("amostras/imagens/DOC-005_receita_ilegivel.png", "image/png"),
}


def documento_oficial(doc_id: str) -> DocumentoParaExtracao:
    caminho_relativo, mime = ORIGINAIS[doc_id]
    caminho = RAIZ / caminho_relativo
    conteudo = caminho.read_bytes()
    return DocumentoParaExtracao(
        documento_id=doc_id,
        arquivo_id="a" * 32,
        nome_original=caminho.name,
        mime_type=mime,
        conteudo=conteudo,
        sha256=hashlib.sha256(conteudo).hexdigest(),
    )


class ExtratorDeFixtureOficial:
    """Substitui SOMENTE I2; não simula as outras três partes do fluxo."""

    def __init__(self, *, alegar_urgencia: bool = False) -> None:
        self.alegar_urgencia = alegar_urgencia
        self.chamadas = 0

    def extrair(self, documento: DocumentoParaExtracao) -> ExtracaoIA:
        self.chamadas += 1
        caminho = RAIZ / "exemplos" / f"{documento.documento_id}_extracao_ia.json"
        extracao = ExtracaoIA.model_validate_json(caminho.read_text(encoding="utf-8"))
        if self.alegar_urgencia:
            # Controle negativo: a LLM fictícia alega urgência no DOC-001,
            # mas o original não contém o marcador expresso de R001.
            extracao.sinais_documentais = SinaisDocumentais(
                marcador_urgencia_explicito=True,
                transcricao_marcador_urgencia="ALERTA SIMULADO PELA LLM",
            )
        return extracao


@pytest.mark.parametrize(
    "doc_id,regra,destino,status,prioridade",
    [
        ("DOC-001", "R005", "prontuario_documental", "processado", "rotina"),
        ("DOC-002", "R001", "fila_prioritaria_avaliacao_humana", "aguardando_auditoria", "possivel_urgencia"),
        ("DOC-005", "R002", "auditoria_humana", "aguardando_auditoria", "indeterminada"),
    ],
)
def test_tres_documentos_oficiais_com_i3_i4_reais(doc_id, regra, destino, status, prioridade):
    extrator = ExtratorDeFixtureOficial()
    servico = montar_servico_i1_i3_i4(extrator=extrator)
    original = documento_oficial(doc_id)

    resultado = servico.executar(original, canal_origem="teste_sintetico")

    assert extrator.chamadas == 1
    assert resultado.documento_id == doc_id
    assert resultado.entrada.sha256 == original.sha256
    assert resultado.entrada.nome_arquivo == original.nome_original
    assert resultado.decisao_roteamento.regra_principal == regra
    assert resultado.decisao_roteamento.destino_principal == destino
    assert resultado.classificacao.nivel_prioridade_documental == prioridade
    assert resultado.status == status
    assert resultado.decisao_roteamento.requer_revisao_humana == (status == "aguardando_auditoria")

    # I3 consulta efetivamente a base Markdown versionada, não um RAG fake.
    assert resultado.rag.status == "consultado"
    assert 1 <= len(resultado.rag.fontes) <= 3
    assert all(f.fonte_id and f.versao and f.titulo for f in resultado.rag.fontes)

    # Sem OCI real, não simular persistência confirmada.
    assert resultado.armazenamento_oci.status == "pendente"
    assert resultado.dados_extraidos == ExtratorDeFixtureOficial().extrair(original).dados_extraidos
    if doc_id == "DOC-005":
        medicamento = resultado.dados_extraidos.medicamentos[0]
        assert medicamento.dosagem_texto is None
        assert medicamento.dosagem_status == "ilegivel"
    if doc_id == "DOC-002":
        assert "R001" in resultado.decisao_roteamento.regras_disparadas


def test_alerta_somente_da_extracao_nao_dispara_r001():
    extrator = ExtratorDeFixtureOficial(alegar_urgencia=True)
    resultado = montar_servico_i1_i3_i4(extrator=extrator).executar(
        documento_oficial("DOC-001"), canal_origem="teste_sintetico"
    )
    assert resultado.decisao_roteamento.regra_principal == "R005"
    assert "R001" not in resultado.decisao_roteamento.regras_disparadas
    assert resultado.classificacao.nivel_prioridade_documental == "rotina"


def test_rag_indisponivel_nao_rebaixa_alerta_do_original():
    class RecuperadorComErro:
        def buscar(self, consulta):
            raise RuntimeError("SEGREDO_RAG_SINTETICO_NAO_EXIBIR")

    resultado = montar_servico_i1_i3_i4(
        extrator=ExtratorDeFixtureOficial(),
        recuperador_referencias=RecuperadorComErro(),
    ).executar(documento_oficial("DOC-002"), canal_origem="teste_sintetico")

    assert resultado.rag.status == "falha"
    assert resultado.rag.erro_codigo == "RAG_ERRO_INTEGRACAO"
    assert resultado.decisao_roteamento.regra_principal == "R001"
    assert resultado.decisao_roteamento.destino_principal == "fila_prioritaria_avaliacao_humana"
    assert resultado.armazenamento_oci.status == "pendente"
    assert "SEGREDO_RAG_SINTETICO_NAO_EXIBIR" not in str(resultado.model_dump())


def test_consulta_rag_minimiza_informacoes_de_paciente():
    class RecuperadorEspiao:
        def __init__(self):
            self.consulta = None

        def buscar(self, consulta):
            self.consulta = consulta
            return RecuperacaoRAG(status="sem_resultados")

    espiao = RecuperadorEspiao()
    resultado = montar_servico_i1_i3_i4(
        extrator=ExtratorDeFixtureOficial(),
        recuperador_referencias=espiao,
    ).executar(documento_oficial("DOC-001"), canal_origem="teste_sintetico")

    assert espiao.consulta is not None
    assert "Marina" not in espiao.consulta.texto
    assert "PF-0001" not in espiao.consulta.texto
    assert "DOC-001" not in espiao.consulta.texto
    assert "Hemoglobina" not in espiao.consulta.texto
    assert resultado.rag.status == "sem_resultados"
    assert resultado.decisao_roteamento.regra_principal == "R005"


def test_hash_original_adulterado_bloqueia_antes_do_extrator():
    extrator = ExtratorDeFixtureOficial()
    original = documento_oficial("DOC-001")
    adulterado = replace(original, sha256="0" * 64)
    servico = montar_servico_i1_i3_i4(extrator=extrator)

    with pytest.raises(FalhaOrquestracao) as erro:
        servico.executar(adulterado, canal_origem="teste_sintetico")

    assert erro.value.codigo == "DOCUMENTO_INVALIDO"
    assert extrator.chamadas == 0


@pytest.mark.parametrize("limite", [0, -1, 11, True, 1.5, "3"])
def test_limite_rag_invalido_rejeitado(limite):
    with pytest.raises(ValueError, match="limite"):
        montar_servico_i1_i3_i4(extrator=ExtratorDeFixtureOficial(), limite_fontes=limite)


def test_extrator_obrigatorio():
    with pytest.raises(TypeError, match="extrator"):
        montar_servico_i1_i3_i4(extrator=None)
