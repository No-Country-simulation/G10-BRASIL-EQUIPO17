"""Testes I1 de integração SIMULADA; nenhuma chamada Gemini, OCI ou LangGraph."""
import hashlib
from pathlib import Path

import pytest

from mediflow.api.triage_service import FalhaOrquestracao, ServicoTriagem
from mediflow.extraction.port import DocumentoParaExtracao
from mediflow_contracts.models import (
    ArmazenamentoOCI,
    ExtracaoIA,
    FonteRAG,
    RecuperacaoRAG,
    ResultadoTriagem,
)
from mediflow_contracts.routing import gerar_exemplo_de_contrato

RAIZ = Path(__file__).resolve().parents[1]
ARQUIVO_ID = "a" * 32


def documento(doc_id, mime="application/pdf", marcador=False):
    # Bytes deliberadamente sintéticos: fake I2 NÃO tenta abrir PDF ou imagem.
    dados = f"AMOSTRA-FICTICIA-{doc_id}".encode("ascii")
    if marcador:
        dados += b" MARCADOR_EXPLICITO_TESTE"
    return DocumentoParaExtracao(
        documento_id=doc_id,
        arquivo_id=ARQUIVO_ID,
        nome_original="teste.pdf" if mime == "application/pdf" else "teste.png",
        mime_type=mime,
        conteudo=dados,
        sha256=hashlib.sha256(dados).hexdigest(),
    )


class ExtratorFake:
    def __init__(self, doc_id):
        self.doc_id = doc_id
        self.chamadas = 0

    def extrair(self, original):
        self.chamadas += 1
        return ExtracaoIA.model_validate_json(
            (RAIZ / f"exemplos/{self.doc_id}_extracao_ia.json").read_text(encoding="utf-8")
        )


class ConfirmadorFake:
    """Simula confirmação no ORIGINAL; não consulta flags ou texto da LLM."""

    def confirmar(self, original):
        return b"MARCADOR_EXPLICITO_TESTE" in original.conteudo


class RAGFake:
    def buscar(self, extracao):
        return RecuperacaoRAG(
            status="consultado",
            fontes=[FonteRAG(fonte_id="R001", titulo="Referencia sintetica", versao="0.1")],
        )


class DecisorFake:
    """Usa APENAS o gerador histórico de exemplo para testar interfaces.

    NÃO substitui motor determinístico executável nem LangGraph do I4.
    """

    def decidir(self, extracao, *, entrada, rag, alerta_textual_confirmado):
        resultado = gerar_exemplo_de_contrato(
            extracao,
            formato=entrada.tipo_entrada,
            alerta_textual_confirmado=alerta_textual_confirmado,
            canal_origem=entrada.canal_origem,
        )
        resultado.entrada = entrada
        resultado.rag = rag
        return resultado


class PersistidorFake:
    """Simula recibo de armazenamento; NÃO confirma gravação na OCI real."""

    def persistir(self, resultado):
        copia = resultado.model_copy(deep=True)
        copia.armazenamento_oci = ArmazenamentoOCI(
            status="confirmado",
            bucket="bucket-sintetico",
            chave_original=f"originais/{resultado.documento_id}/{ARQUIVO_ID}.pdf",
            chave_resultado=f"resultados/{resultado.documento_id}/{ARQUIVO_ID}/{'b' * 32}.json",
            chave_historico=f"historicos/{resultado.documento_id}/{ARQUIVO_ID}/{'b' * 32}.json",
        )
        return copia


def servico(doc_id="DOC-001", *, recuperador=None, persistidor=None):
    return ServicoTriagem(
        extrator=ExtratorFake(doc_id),
        confirmador=ConfirmadorFake(),
        decisor=DecisorFake(),
        recuperador=recuperador,
        persistidor=persistidor,
    )


@pytest.mark.parametrize(
    "doc_id,mime,marcador,regra,destino",
    [
        ("DOC-001", "application/pdf", False, "R005", "prontuario_documental"),
        ("DOC-002", "application/pdf", True, "R001", "fila_prioritaria_avaliacao_humana"),
        ("DOC-005", "image/png", False, "R002", "auditoria_humana"),
    ],
)
def test_tres_cenarios_contrato(doc_id, mime, marcador, regra, destino):
    resultado = servico(doc_id, recuperador=RAGFake()).executar(
        documento(doc_id, mime, marcador), canal_origem="teste_sintetico"
    )
    assert resultado.documento_id == doc_id
    assert resultado.decisao_roteamento.regra_principal == regra
    assert resultado.decisao_roteamento.destino_principal == destino
    assert resultado.rag.status == "consultado"
    assert resultado.armazenamento_oci.status == "pendente"
    assert resultado.entrada.sha256 is not None
    assert resultado.entrada.nome_arquivo
    if regra in {"R001", "R002"}:
        assert resultado.decisao_roteamento.requer_revisao_humana


def test_sinal_da_llm_sozinho_nao_aciona_r001():
    # DOC-002 da fixture indica urgência na LLM, mas bytes não confirmam.
    resultado = servico("DOC-002").executar(documento("DOC-002"), canal_origem="teste")
    assert resultado.decisao_roteamento.regra_principal != "R001"


def test_extracao_com_documento_id_diferente_interrompe_pipeline():
    with pytest.raises(FalhaOrquestracao, match="DOCUMENTO_DIVERGENTE"):
        servico("DOC-002").executar(documento("DOC-001"), canal_origem="teste")


def test_bytes_adulterados_sao_rejeitados_antes_da_extracao():
    doc = documento("DOC-001")
    doc = DocumentoParaExtracao(
        documento_id=doc.documento_id, arquivo_id=doc.arquivo_id,
        nome_original=doc.nome_original, mime_type=doc.mime_type,
        conteudo=b"alterado", sha256=doc.sha256,
    )
    extrator = ExtratorFake("DOC-001")
    pipeline = ServicoTriagem(extrator, ConfirmadorFake(), DecisorFake())
    with pytest.raises(FalhaOrquestracao, match="DOCUMENTO_INVALIDO"):
        pipeline.executar(doc, canal_origem="teste")
    assert extrator.chamadas == 0


def test_rag_falha_nao_impede_regras_e_fica_registrado():
    class RAGQueFalha:
        def buscar(self, extracao):
            raise RuntimeError("token ficticio secreto")

    resultado = servico("DOC-001", recuperador=RAGQueFalha()).executar(
        documento("DOC-001"), canal_origem="teste"
    )
    assert resultado.rag.status == "falha"
    assert resultado.rag.erro_codigo == "RAG_ERRO_INTEGRACAO"
    assert resultado.decisao_roteamento.regra_principal == "R005"


def test_decisor_nao_pode_acionar_r001_sem_confirmacao():
    class DecisorInseguro(DecisorFake):
        def decidir(self, extracao, *, entrada, rag, alerta_textual_confirmado):
            return super().decidir(
                extracao, entrada=entrada, rag=rag, alerta_textual_confirmado=True
            )

    pipeline = ServicoTriagem(ExtratorFake("DOC-002"), ConfirmadorFake(), DecisorInseguro())
    with pytest.raises(FalhaOrquestracao, match="ALERTA_SEM_CONFIRMACAO_INDEPENDENTE"):
        pipeline.executar(documento("DOC-002"), canal_origem="teste")


def test_confirmador_que_falha_impede_decisao():
    class ConfirmadorQueFalha:
        def confirmar(self, original):
            raise RuntimeError("falha no leitor")

    pipeline = ServicoTriagem(ExtratorFake("DOC-001"), ConfirmadorQueFalha(), DecisorFake())
    with pytest.raises(FalhaOrquestracao, match="CONFIRMACAO_INDISPONIVEL"):
        pipeline.executar(documento("DOC-001"), canal_origem="teste")


def test_sem_persistidor_storage_permanece_pendente():
    resultado = servico().executar(documento("DOC-001"), canal_origem="teste")
    assert resultado.armazenamento_oci.status == "pendente"


def test_persistidor_simulado_retorna_status_confirmado_sem_oci_real():
    resultado = servico(persistidor=PersistidorFake()).executar(
        documento("DOC-001"), canal_origem="teste"
    )
    assert resultado.armazenamento_oci.status == "confirmado"
    assert resultado.armazenamento_oci.chave_historico


def test_persistidor_sem_confirmacao_e_rejeitado():
    class PersistidorIncompleto:
        def persistir(self, resultado):
            return resultado

    with pytest.raises(FalhaOrquestracao, match="PERSISTENCIA_NAO_CONFIRMADA"):
        servico(persistidor=PersistidorIncompleto()).executar(
            documento("DOC-001"), canal_origem="teste"
        )


def test_persistidor_que_falha_nao_expoe_erro_remoto():
    class PersistidorQueFalha:
        def persistir(self, resultado):
            raise RuntimeError("SEGREDO_FAKE_OCI")

    with pytest.raises(FalhaOrquestracao) as e:
        servico(persistidor=PersistidorQueFalha()).executar(
            documento("DOC-001"), canal_origem="teste"
        )
    assert e.value.codigo == "PERSISTENCIA_INDISPONIVEL"
    assert "SEGREDO_FAKE_OCI" not in str(e.value)


def test_decisor_nao_pode_alterar_dados_extraidos():
    class DecisorQueAltera(DecisorFake):
        def decidir(self, extracao, *, entrada, rag, alerta_textual_confirmado):
            r = super().decidir(
                extracao, entrada=entrada, rag=rag,
                alerta_textual_confirmado=alerta_textual_confirmado,
            )
            r.dados_extraidos.descricao_documento = "Inventado pelo decisor"
            return r

    pipeline = ServicoTriagem(ExtratorFake("DOC-001"), ConfirmadorFake(), DecisorQueAltera())
    with pytest.raises(FalhaOrquestracao, match="RESULTADO_INCONSISTENTE"):
        pipeline.executar(documento("DOC-001"), canal_origem="teste")


def test_sem_recuperador_registra_nao_consultado():
    resultado = servico().executar(documento("DOC-001"), canal_origem="teste")
    assert resultado.rag.status == "nao_consultado"
    assert resultado.rag.fontes == []


def test_recuperador_nao_consegue_mutar_extracao_original():
    class RAGQueAltera:
        def buscar(self, extracao):
            extracao.tipo_documento = "outro_desconhecido"
            extracao.dados_extraidos.descricao_documento = "Alteracao indevida"
            return RecuperacaoRAG(status="sem_resultados")

    resultado = servico(recuperador=RAGQueAltera()).executar(
        documento("DOC-001"), canal_origem="teste"
    )
    assert resultado.classificacao.tipo_documento == "laudo_laboratorial"
    assert resultado.decisao_roteamento.regra_principal == "R005"


def test_mime_nao_suportado_rejeitado_antes_da_extracao():
    doc = documento("DOC-001", mime="application/octet-stream")
    extrator = ExtratorFake("DOC-001")
    pipeline = ServicoTriagem(extrator, ConfirmadorFake(), DecisorFake())
    with pytest.raises(FalhaOrquestracao, match="DOCUMENTO_INVALIDO"):
        pipeline.executar(doc, canal_origem="teste")
    assert extrator.chamadas == 0


def test_confirmador_nao_booleano_e_rejeitado():
    class ConfirmadorIncorreto:
        def confirmar(self, original):
            return "false"

    pipeline = ServicoTriagem(ExtratorFake("DOC-001"), ConfirmadorIncorreto(), DecisorFake())
    with pytest.raises(FalhaOrquestracao, match="CONFIRMACAO_INVALIDA"):
        pipeline.executar(documento("DOC-001"), canal_origem="teste")


def test_persistidor_nao_pode_trocar_a_decisao():
    class PersistidorIncorreto(PersistidorFake):
        def persistir(self, resultado):
            copia = super().persistir(resultado)
            copia.decisao_roteamento.regra_principal = "R003"
            return copia

    with pytest.raises(FalhaOrquestracao, match="PERSISTENCIA_NAO_CONFIRMADA"):
        servico(persistidor=PersistidorIncorreto()).executar(
            documento("DOC-001"), canal_origem="teste"
        )


def test_decisor_nao_pode_omitir_referencias_rag():
    class DecisorSemFontes(DecisorFake):
        def decidir(self, extracao, *, entrada, rag, alerta_textual_confirmado):
            resultado = super().decidir(
                extracao, entrada=entrada, rag=rag,
                alerta_textual_confirmado=alerta_textual_confirmado,
            )
            resultado.rag = RecuperacaoRAG(status="nao_consultado")
            return resultado

    pipeline = ServicoTriagem(
        ExtratorFake("DOC-001"), ConfirmadorFake(), DecisorSemFontes(), RAGFake()
    )
    with pytest.raises(FalhaOrquestracao, match="RESULTADO_INCONSISTENTE"):
        pipeline.executar(documento("DOC-001"), canal_origem="teste")
