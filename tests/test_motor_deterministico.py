"""Testes do motor determinístico de regras, sem Gemini, OCI ou LangGraph."""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path

import pymupdf
import pytest
import yaml
from PIL import Image

from mediflow.api.triage_service import FalhaOrquestracao, ServicoTriagem
from mediflow.extraction.port import DocumentoParaExtracao
from mediflow.rules.confirmador_alerta import ConfirmadorAlertaOriginal
from mediflow.rules.motor_deterministico import MotorRegrasDeterministico
from mediflow_contracts.models import EntradaProcessada, ExtracaoIA, RecuperacaoRAG

RAIZ = Path(__file__).resolve().parents[1]
ARQUIVO_ID = "a" * 32


def ler_extracao(doc_id: str) -> ExtracaoIA:
    return ExtracaoIA.model_validate_json(
        (RAIZ / "exemplos" / f"{doc_id}_extracao_ia.json").read_text(encoding="utf-8")
    )


def entrada(tipo: str = "pdf") -> EntradaProcessada:
    return EntradaProcessada(tipo_entrada=tipo, canal_origem="teste-sintetico")


def decidir(doc_id: str, confirmado: bool = False, *, rag=None, tipo="pdf"):
    return MotorRegrasDeterministico().decidir(
        ler_extracao(doc_id), entrada=entrada(tipo),
        rag=rag if rag is not None else RecuperacaoRAG(),
        alerta_textual_confirmado=confirmado,
    )


@pytest.mark.parametrize("doc_id,alerta,regra,destino,status,tipo", [
    ("DOC-001", False, "R005", "prontuario_documental", "processado", "pdf"),
    ("DOC-002", True, "R001", "fila_prioritaria_avaliacao_humana", "aguardando_auditoria", "pdf"),
    ("DOC-005", False, "R002", "auditoria_humana", "aguardando_auditoria", "png"),
])
def test_tres_cenarios_oficiais(doc_id, alerta, regra, destino, status, tipo):
    original = ler_extracao(doc_id)
    resultado = decidir(doc_id, alerta, tipo=tipo)
    assert resultado.documento_id == doc_id
    assert resultado.classificacao.tipo_documento == original.tipo_documento
    assert resultado.decisao_roteamento.regra_principal == regra
    assert resultado.decisao_roteamento.destino_principal == destino
    assert resultado.status == status
    assert resultado.decisao_roteamento.requer_revisao_humana == (status == "aguardando_auditoria")
    assert resultado.entrada == entrada(tipo)
    assert resultado.dados_extraidos == original.dados_extraidos
    assert resultado.evidencias == original.evidencias
    assert resultado.armazenamento_oci.status == "pendente"
    assert resultado.classificacao.indicador_qualidade.metodo == "nao_calculado"
    assert resultado.classificacao.indicador_qualidade.valor is None


def test_prioridade_urgente_supera_ambiguidade_sem_apagar_r002():
    original = ler_extracao("DOC-002").model_copy(deep=True)
    bruto = original.model_dump()
    bruto["dados_extraidos"]["paciente"]["nome"] = None
    bruto["dados_extraidos"]["paciente"]["nome_status"] = "ilegivel"
    original = ExtracaoIA.model_validate(bruto)
    resultado = MotorRegrasDeterministico().decidir(
        original, entrada=entrada(), rag=RecuperacaoRAG(),
        alerta_textual_confirmado=True,
    )
    assert resultado.decisao_roteamento.regra_principal == "R001"
    assert "R002" in resultado.decisao_roteamento.regras_disparadas
    assert "paciente.nome" in resultado.validacao.campos_ilegiveis
    assert resultado.decisao_roteamento.requer_revisao_humana is True


def test_marcador_alegado_pela_llm_nao_confirma_urgencia():
    # DOC-002 possui flag da LLM, mas o I4 recebe confirmação INDEPENDENTE falsa.
    resultado = decidir("DOC-002", False)
    assert resultado.decisao_roteamento.regra_principal != "R001"
    assert "R001" not in resultado.decisao_roteamento.regras_disparadas
    assert not resultado.decisao_roteamento.alertas


def test_dosagem_ilegivel_permanece_nula():
    resultado = decidir("DOC-005", False, tipo="png")
    assert resultado.dados_extraidos.medicamentos[0].dosagem_texto is None
    assert "medicamentos[0].dosagem_texto" in resultado.validacao.campos_ilegiveis


def test_rag_indisponivel_nao_altera_decisao():
    rag = RecuperacaoRAG(status="falha", erro_codigo="RAG_ERRO_INTEGRACAO")
    resultado = decidir("DOC-002", True, rag=rag)
    assert resultado.rag == rag
    assert resultado.decisao_roteamento.regra_principal == "R001"


def test_r003_solicitacao_completa():
    extra = ler_extracao("DOC-001").model_copy(deep=True)
    extra.tipo_documento = "solicitacao_exame"
    extra.dados_extraidos.procedimentos = ["Exame fictício"]
    r = MotorRegrasDeterministico().decidir(
        extra, entrada=entrada(), rag=RecuperacaoRAG(),
        alerta_textual_confirmado=False,
    )
    assert r.decisao_roteamento.regra_principal == "R003"


def test_r004_receituario_completo():
    extra = ler_extracao("DOC-005").model_copy(deep=True)
    bruto = extra.model_dump()
    bruto["dados_extraidos"]["medicamentos"][0]["dosagem_texto"] = "Dose sintética legível"
    bruto["dados_extraidos"]["medicamentos"][0]["dosagem_status"] = "legivel"
    extra = ExtracaoIA.model_validate(bruto)
    r = MotorRegrasDeterministico().decidir(
        extra, entrada=entrada("png"), rag=RecuperacaoRAG(),
        alerta_textual_confirmado=False,
    )
    assert r.decisao_roteamento.regra_principal == "R004"
    assert r.decisao_roteamento.destino_principal == "fila_farmacia_documental"


def test_r006_tipo_desconhecido():
    extra = ler_extracao("DOC-001").model_copy(deep=True)
    extra.tipo_documento = "outro_desconhecido"
    r = MotorRegrasDeterministico().decidir(
        extra, entrada=entrada(), rag=RecuperacaoRAG(),
        alerta_textual_confirmado=False,
    )
    assert r.decisao_roteamento.regra_principal == "R006"
    assert r.decisao_roteamento.requer_revisao_humana
    assert r.validacao.integridade_documental == "indeterminada"


def test_aviso_profissional_ausente_nao_converte_rotina_em_urgencia():
    extra = ler_extracao("DOC-001").model_copy(deep=True)
    extra.dados_extraidos.profissional.nome = None
    r = MotorRegrasDeterministico().decidir(
        extra, entrada=entrada(), rag=RecuperacaoRAG(),
        alerta_textual_confirmado=False,
    )
    assert r.decisao_roteamento.regra_principal == "R005"
    assert any("V003" in aviso for aviso in r.validacao.observacoes)


def test_lista_vazia_de_medicamentos_exige_auditoria_sem_duplicar():
    extra = ler_extracao("DOC-005").model_copy(deep=True)
    extra.dados_extraidos.medicamentos = []
    r = MotorRegrasDeterministico().decidir(
        extra, entrada=entrada("png"), rag=RecuperacaoRAG(),
        alerta_textual_confirmado=False,
    )
    assert r.decisao_roteamento.regra_principal == "R002"
    assert r.validacao.campos_ausentes.count("medicamentos[]") == 1


def test_rejeita_parametros_invalidos():
    motor = MotorRegrasDeterministico()
    with pytest.raises(TypeError):
        motor.decidir(ler_extracao("DOC-001"), entrada=entrada(),
                     rag=RecuperacaoRAG(), alerta_textual_confirmado=1)


def test_yaml_alterado_para_precedencia_insegura_rejeitado(tmp_path):
    original = yaml.safe_load((RAIZ / "rules" / "roteamento.yaml").read_text("utf-8"))
    original["precedencia"] = list(reversed(original["precedencia"]))
    arquivo = tmp_path / "roteamento.yaml"
    arquivo.write_text(yaml.safe_dump(original, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="Precedência"):
        MotorRegrasDeterministico(arquivo_roteamento=arquivo)


def test_yaml_sem_configuracao_da_urgencia_rejeitado(tmp_path):
    original = yaml.safe_load((RAIZ / "rules" / "roteamento.yaml").read_text("utf-8"))
    original["regras"][0]["requer_revisao_humana"] = False
    arquivo = tmp_path / "roteamento.yaml"
    arquivo.write_text(yaml.safe_dump(original, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="R001"):
        MotorRegrasDeterministico(arquivo_roteamento=arquivo)


def test_yaml_ambiguidade_nao_pode_virar_rotina(tmp_path):
    original = yaml.safe_load((RAIZ / "rules" / "roteamento.yaml").read_text("utf-8"))
    original["regras"][1]["destino"] = "prontuario_documental"
    original["regras"][1]["requer_revisao_humana"] = False
    arquivo = tmp_path / "roteamento.yaml"
    arquivo.write_text(yaml.safe_dump(original, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="R002"):
        MotorRegrasDeterministico(arquivo_roteamento=arquivo)


def test_laudo_imagem_sem_conclusao_aciona_r002():
    extra = ler_extracao("DOC-002").model_copy(deep=True)
    extra.dados_extraidos.exame.conclusao = None
    resultado = MotorRegrasDeterministico().decidir(
        extra, entrada=entrada(), rag=RecuperacaoRAG(),
        alerta_textual_confirmado=False,
    )
    assert resultado.decisao_roteamento.regra_principal == "R002"
    assert "exame.conclusao" in resultado.validacao.campos_ausentes


def test_nome_com_espacos_nao_conta_como_legivel():
    original = ler_extracao("DOC-001").model_dump()
    original["dados_extraidos"]["paciente"]["nome"] = "   "
    extra = ExtracaoIA.model_validate(original)
    resultado = MotorRegrasDeterministico().decidir(
        extra, entrada=entrada(), rag=RecuperacaoRAG(),
        alerta_textual_confirmado=False,
    )
    assert resultado.decisao_roteamento.regra_principal == "R002"


def test_texto_urgente_com_travessao_reconhecido():
    doc = documento_pdf("DOC-002", "ACHADO CRITICO - URGENTE")
    # Simula variação tipográfica na extração, sem rede ou consulta à LLM.
    from mediflow.rules.confirmador_alerta import _normalizar
    assert _normalizar("ACHADO CRÍTICO — URGENTE") == "ACHADO CRITICO - URGENTE"
    assert ConfirmadorAlertaOriginal().confirmar(doc) is True


def documento_pdf(doc_id: str, texto: str) -> DocumentoParaExtracao:
    pdf = pymupdf.open()
    pdf.new_page().insert_text((50, 72), texto)
    conteudo = pdf.tobytes()
    pdf.close()
    return DocumentoParaExtracao(
        documento_id=doc_id, arquivo_id=ARQUIVO_ID,
        nome_original="amostra.pdf", mime_type="application/pdf",
        conteudo=conteudo, sha256=sha256(conteudo).hexdigest(),
    )


def test_confirmacao_independente_em_pdf_de_alerta_explicito():
    documento = documento_pdf("DOC-002", "ACHADO CRITICO - URGENTE. Comunicar imediatamente")
    assert ConfirmadorAlertaOriginal().confirmar(documento) is True


def test_confirmador_nao_transforma_negacao_em_urgencia():
    documento = documento_pdf("DOC-001", "Documento sem declaracao de urgencia.")
    assert ConfirmadorAlertaOriginal().confirmar(documento) is False


def test_pdf_corrompido_falha_fechado():
    conteudo = b"%PDF dados corrompidos"
    documento = DocumentoParaExtracao(
        "DOC-002", ARQUIVO_ID, "amostra.pdf", "application/pdf",
        conteudo, sha256(conteudo).hexdigest(),
    )
    with pytest.raises(Exception):
        ConfirmadorAlertaOriginal().confirmar(documento)


def test_confirmador_png_consulta_ocr_original_sem_llm(monkeypatch):
    conteudo = BytesIO()
    Image.new("RGB", (200, 80), "white").save(conteudo, format="PNG")
    bruto = conteudo.getvalue()
    documento = DocumentoParaExtracao(
        "DOC-005", ARQUIVO_ID, "amostra.png", "image/png", bruto, sha256(bruto).hexdigest()
    )
    chamadas = []

    def extrator_ocr(bytes_original):
        chamadas.append(bytes_original)
        return "Receita: Medicamento Alfa. Sem aviso prioritario."

    monkeypatch.setattr("mediflow.rules.confirmador_alerta.extrair_texto_imagem", extrator_ocr)
    assert ConfirmadorAlertaOriginal().confirmar(documento) is False
    assert chamadas == [bruto]


class ExtratorDeFixtures:
    def extrair(self, documento):
        return ler_extracao(documento.documento_id)


@pytest.mark.parametrize("doc_id,texto,regra", [
    ("DOC-001", "Documento sem declaracao de urgencia", "R005"),
    ("DOC-002", "ACHADO CRITICO - URGENTE. Comunicar imediatamente", "R001"),
])
def test_integracao_com_servico_i1_usando_extrator_fixture(doc_id, texto, regra):
    documento = documento_pdf(doc_id, texto)
    servico = ServicoTriagem(
        extrator=ExtratorDeFixtures(),
        confirmador=ConfirmadorAlertaOriginal(),
        decisor=MotorRegrasDeterministico(),
    )
    resultado = servico.executar(documento, canal_origem="teste-i4")
    assert resultado.decisao_roteamento.regra_principal == regra
    assert resultado.armazenamento_oci.status == "pendente"
    assert resultado.entrada.sha256 == documento.sha256


def test_falha_confirmacao_no_servico_i1_nao_rota_como_rotina():
    conteudo = b"PDF invalido"
    documento = DocumentoParaExtracao(
        "DOC-001", ARQUIVO_ID, "amostra.pdf", "application/pdf",
        conteudo, sha256(conteudo).hexdigest(),
    )
    servico = ServicoTriagem(
        extrator=ExtratorDeFixtures(),
        confirmador=ConfirmadorAlertaOriginal(),
        decisor=MotorRegrasDeterministico(),
    )
    with pytest.raises(FalhaOrquestracao) as e:
        servico.executar(documento, canal_origem="teste-i4")
    assert e.value.codigo == "CONFIRMACAO_INDISPONIVEL"
    assert e.value.etapa == "alerta"


def test_configuracao_v002_nao_pode_perder_auditoria(tmp_path):
    origem = yaml.safe_load((RAIZ / "rules" / "validacao.yaml").read_text("utf-8"))
    origem["validacoes"][1]["encaminhamento"] = "manter_aviso"
    arquivo = tmp_path / "validacao.yaml"
    arquivo.write_text(yaml.safe_dump(origem, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="V002"):
        MotorRegrasDeterministico(arquivo_validacao=arquivo)


def test_marcador_negado_nao_aciona_alerta():
    original = documento_pdf("DOC-001", "SEM ACHADO CRITICO - URGENTE")
    assert ConfirmadorAlertaOriginal().confirmar(original) is False


def test_confirmador_rejeita_hash_de_original_adulterado():
    original = documento_pdf("DOC-001", "Documento sintetico sem prioridade")
    alterado = DocumentoParaExtracao(
        original.documento_id, original.arquivo_id, original.nome_original,
        original.mime_type, original.conteudo, "a" * 64,
    )
    with pytest.raises(ValueError, match="hash"):
        ConfirmadorAlertaOriginal().confirmar(alterado)


def test_motor_retorna_regra_e_destino_coerentes_para_r005():
    resultado = decidir("DOC-001", False)
    assert resultado.decisao_roteamento.regra_principal == "R005"
    assert resultado.decisao_roteamento.destino_principal == "prontuario_documental"
