"""Homologação I1/I2 sem rede: OCR real, cliente Gemini simulado e I4 demonstrativo.

Exclusivamente documentos sintéticos. Não executa Gemini, OCI ou LangGraph reais.
Os testes das regras utilizam o gerador histórico de exemplos, NÃO o I4 definitivo.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pymupdf
import pytest
from PIL import Image, ImageDraw, ImageFont

from mediflow.api.triage_service import FalhaOrquestracao, ServicoTriagem
from mediflow.extraction.gemini_extractor import ExtratorGemini
from mediflow.extraction.port import DocumentoParaExtracao
from mediflow_contracts.models import (
    DadosExtraidos,
    Evidencia,
    Exame,
    ExtracaoIA,
    Medicamento,
    Paciente,
    ResultadoLaboratorial,
    SinaisDocumentais,
)
from mediflow_contracts.routing import gerar_exemplo_de_contrato


class ConfirmadorFalso:
    """Simula I4 sem validar alegações de urgência vindas da LLM."""

    def __init__(self):
        self.chamadas = 0

    def confirmar(self, documento):
        self.chamadas += 1
        return False


class DecisorDemonstrativo:
    """Somente contrato de testes; NÃO representa o decisor definitivo do I4."""

    def __init__(self):
        self.chamadas = 0

    def decidir(self, extracao, *, entrada, rag, alerta_textual_confirmado):
        self.chamadas += 1
        resultado = gerar_exemplo_de_contrato(
            extracao,
            formato=entrada.tipo_entrada,
            alerta_textual_confirmado=alerta_textual_confirmado,
            canal_origem=entrada.canal_origem,
        )
        resultado.entrada = entrada
        resultado.rag = rag
        return resultado


def documento_sintetico(doc_id, conteudo, mime_type, nome_arquivo):
    return DocumentoParaExtracao(
        documento_id=doc_id,
        arquivo_id="a" * 32,
        nome_original=nome_arquivo,
        mime_type=mime_type,
        conteudo=conteudo,
        sha256=hashlib.sha256(conteudo).hexdigest(),
    )


def pdf_digital_sintetico():
    pdf = pymupdf.open()
    try:
        pagina = pdf.new_page()
        pagina.insert_text((50, 70), "LAUDO LABORATORIAL FICTICIO")
        pagina.insert_text((50, 100), "Paciente: Pessoa Ficticia")
        pagina.insert_text((50, 130), "Exame: Hemograma")
        pagina.insert_text((50, 160), "Hemoglobina: 13 g/dL")
        pagina.insert_text((50, 190), "Conclusao: Sem alteracoes.")
        return pdf.tobytes()
    finally:
        pdf.close()


def png_sintetico():
    imagem = Image.new("RGB", (1400, 310), color="white")
    desenho = ImageDraw.Draw(imagem)
    desenho.text(
        (35, 115),
        "RECEITUARIO FICTICIO PARA TESTE",
        fill="black",
        font=ImageFont.load_default(size=48),
    )
    buffer = BytesIO()
    imagem.save(buffer, format="PNG")
    return buffer.getvalue()


def extracao_laudo(doc_id="DOC-001", *, evidencia_valida=True, alerta_llm=False):
    return ExtracaoIA(
        documento_id=doc_id,
        tipo_documento="laudo_laboratorial",
        dados_extraidos=DadosExtraidos(
            paciente=Paciente(nome="Pessoa Ficticia", nome_status="legivel"),
            exame=Exame(
                nome="Hemograma",
                conclusao="Sem alteracoes.",
                resultados=[ResultadoLaboratorial(parametro="Hemoglobina", valor_texto="13", unidade="g/dL")],
            ),
        ),
        evidencias=[
            Evidencia(
                campo="exame.conclusao",
                trecho_documento=(
                    "Sem alteracoes." if evidencia_valida else "Diagnostico inexistente no documento"
                ),
                pagina=1,
            )
        ],
        sinais_documentais=SinaisDocumentais(
            marcador_urgencia_explicito=alerta_llm,
            transcricao_marcador_urgencia="ALERTA INVENTADO" if alerta_llm else None,
        ),
    )


def extracao_receituario():
    return ExtracaoIA(
        documento_id="DOC-005",
        tipo_documento="receituario",
        dados_extraidos=DadosExtraidos(
            paciente=Paciente(nome="Pessoa Ficticia", nome_status="legivel"),
            medicamentos=[Medicamento(nome="Medicamento Ficticio", dosagem_status="ilegivel")],
        ),
    )


def criar_extrator_com_cliente_simulado(monkeypatch, *, resposta=None, falha=None):
    """Instancia a classe REAL do I2, mas substitui somente a API externa."""
    monkeypatch.setenv("GEMINI_API_KEY", "CHAVE_FICTICIA_EXCLUSIVA_DOS_TESTES")
    cliente = MagicMock()
    if falha is None:
        cliente.models.generate_content.return_value = SimpleNamespace(
            text=json.dumps(resposta.model_dump(mode="json"), ensure_ascii=False)
        )
    else:
        cliente.models.generate_content.side_effect = falha
    monkeypatch.setattr("mediflow.extraction.gemini_extractor.genai.Client", lambda **_: cliente)
    return ExtratorGemini(), cliente


def criar_servico(extrator):
    confirmador = ConfirmadorFalso()
    decisor = DecisorDemonstrativo()
    return ServicoTriagem(extrator=extrator, confirmador=confirmador, decisor=decisor), confirmador, decisor


def test_pdf_digital_i2_real_ocr_i1_orquestrado_com_gemini_simulado(monkeypatch):
    documento = documento_sintetico(
        "DOC-001", pdf_digital_sintetico(), "application/pdf", "laudo-ficticio.pdf"
    )
    extrator, cliente = criar_extrator_com_cliente_simulado(
        monkeypatch, resposta=extracao_laudo()
    )
    servico, confirmador, decisor = criar_servico(extrator)

    resultado = servico.executar(documento, canal_origem="teste_sintetico")

    assert resultado.documento_id == "DOC-001"
    assert resultado.entrada.sha256 == documento.sha256
    assert resultado.entrada.nome_arquivo == documento.nome_original
    assert resultado.entrada.tipo_entrada == "pdf"
    assert resultado.decisao_roteamento.regra_principal == "R005"
    assert resultado.status == "processado"
    assert resultado.evidencias[0].pagina == 1
    assert resultado.armazenamento_oci.status == "pendente"
    assert resultado.rag.status == "nao_consultado"
    assert confirmador.chamadas == decisor.chamadas == 1
    cliente.models.generate_content.assert_called_once()
    requisicao = cliente.models.generate_content.call_args.kwargs["contents"]
    assert "[Página 1]" in requisicao
    assert "Conclusao: Sem alteracoes." in requisicao


def test_imagem_png_passa_por_ocr_real_e_gera_pendencia_documental(monkeypatch):
    documento = documento_sintetico(
        "DOC-005", png_sintetico(), "image/png", "receituario-ficticio.png"
    )
    extrator, cliente = criar_extrator_com_cliente_simulado(
        monkeypatch, resposta=extracao_receituario()
    )
    servico, _, _ = criar_servico(extrator)

    resultado = servico.executar(documento, canal_origem="teste_sintetico")

    assert resultado.documento_id == "DOC-005"
    assert resultado.decisao_roteamento.regra_principal == "R002"
    assert resultado.status == "aguardando_auditoria"
    assert resultado.entrada.tipo_entrada == "png"
    assert resultado.armazenamento_oci.status == "pendente"
    requisicao = cliente.models.generate_content.call_args.kwargs["contents"]
    assert "RECEITUARIO" in requisicao.upper()


def test_alegacao_de_urgencia_da_llm_nao_substitui_confirmacao_independente(monkeypatch):
    documento = documento_sintetico(
        "DOC-001", pdf_digital_sintetico(), "application/pdf", "laudo-ficticio.pdf"
    )
    extrator, _ = criar_extrator_com_cliente_simulado(
        monkeypatch, resposta=extracao_laudo(alerta_llm=True)
    )
    servico, confirmador, _ = criar_servico(extrator)

    resultado = servico.executar(documento, canal_origem="teste_sintetico")

    assert confirmador.chamadas == 1
    assert resultado.decisao_roteamento.regra_principal == "R005"
    assert resultado.classificacao.nivel_prioridade_documental == "rotina"


def test_evidencia_inventada_pelo_modelo_bloqueia_a_orquestracao(monkeypatch):
    documento = documento_sintetico(
        "DOC-001", pdf_digital_sintetico(), "application/pdf", "laudo-ficticio.pdf"
    )
    extrator, _ = criar_extrator_com_cliente_simulado(
        monkeypatch, resposta=extracao_laudo(evidencia_valida=False)
    )
    servico, confirmador, decisor = criar_servico(extrator)

    with pytest.raises(FalhaOrquestracao) as erro:
        servico.executar(documento, canal_origem="teste_sintetico")

    assert erro.value.codigo == "EXTRACAO_INVALIDA_OU_INDISPONIVEL"
    assert erro.value.etapa == "extracao"
    assert confirmador.chamadas == decisor.chamadas == 0
    assert "Diagnostico inexistente" not in str(erro.value)


def test_documento_id_divergente_da_llm_interrompe_o_fluxo(monkeypatch):
    documento = documento_sintetico(
        "DOC-001", pdf_digital_sintetico(), "application/pdf", "laudo-ficticio.pdf"
    )
    extrator, _ = criar_extrator_com_cliente_simulado(
        monkeypatch, resposta=extracao_laudo(doc_id="DOC-999")
    )
    servico, confirmador, decisor = criar_servico(extrator)

    with pytest.raises(FalhaOrquestracao) as erro:
        servico.executar(documento, canal_origem="teste_sintetico")

    assert erro.value.codigo == "EXTRACAO_INVALIDA_OU_INDISPONIVEL"
    assert confirmador.chamadas == decisor.chamadas == 0


def test_falha_da_api_gemini_e_sanitizada_pelo_i1(monkeypatch):
    documento = documento_sintetico(
        "DOC-001", pdf_digital_sintetico(), "application/pdf", "laudo-ficticio.pdf"
    )
    extrator, cliente = criar_extrator_com_cliente_simulado(
        monkeypatch, falha=RuntimeError("SEGREDO_GEMINI_SIMULADO_NAO_EXIBIR")
    )
    servico, confirmador, decisor = criar_servico(extrator)

    with pytest.raises(FalhaOrquestracao) as erro:
        servico.executar(documento, canal_origem="teste_sintetico")

    cliente.models.generate_content.assert_called_once()
    assert erro.value.codigo == "EXTRACAO_INVALIDA_OU_INDISPONIVEL"
    assert "SEGREDO_GEMINI_SIMULADO_NAO_EXIBIR" not in str(erro.value)
    assert confirmador.chamadas == decisor.chamadas == 0


def test_sha256_adulterado_bloqueia_antes_de_chamar_o_i2(monkeypatch):
    documento = documento_sintetico(
        "DOC-001", pdf_digital_sintetico(), "application/pdf", "laudo-ficticio.pdf"
    )
    adulterado = replace(documento, sha256="0" * 64)
    extrator, cliente = criar_extrator_com_cliente_simulado(
        monkeypatch, resposta=extracao_laudo()
    )
    servico, confirmador, decisor = criar_servico(extrator)

    with pytest.raises(FalhaOrquestracao) as erro:
        servico.executar(adulterado, canal_origem="teste_sintetico")

    assert erro.value.codigo == "DOCUMENTO_INVALIDO"
    cliente.models.generate_content.assert_not_called()
    assert confirmador.chamadas == decisor.chamadas == 0


def test_falha_de_ocr_e_interrompida_sem_expor_detalhes(monkeypatch):
    documento = documento_sintetico(
        "DOC-005", png_sintetico(), "image/png", "receituario-ficticio.png"
    )
    extrator, cliente = criar_extrator_com_cliente_simulado(
        monkeypatch, resposta=extracao_receituario()
    )
    monkeypatch.setattr(
        "mediflow.extraction.gemini_extractor.extrair_texto_imagem",
        lambda _: (_ for _ in ()).throw(RuntimeError("SEGREDO_OCR_SIMULADO_NAO_EXIBIR")),
    )
    servico, confirmador, decisor = criar_servico(extrator)

    with pytest.raises(FalhaOrquestracao) as erro:
        servico.executar(documento, canal_origem="teste_sintetico")

    assert erro.value.codigo == "EXTRACAO_INVALIDA_OU_INDISPONIVEL"
    assert "SEGREDO_OCR_SIMULADO_NAO_EXIBIR" not in str(erro.value)
    cliente.models.generate_content.assert_not_called()
    assert confirmador.chamadas == decisor.chamadas == 0
