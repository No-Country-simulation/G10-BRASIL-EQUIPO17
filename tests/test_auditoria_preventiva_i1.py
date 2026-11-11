"""Testes preventivos de consistência das interfaces do I1.

Executados com dados sintéticos e componentes simulados.
Não acessam Gemini, OCI ou LangGraph reais.

A validação entre regra e destino utiliza o catálogo determinístico do I4.
"""

import pytest

from mediflow.api.triage_service import FalhaOrquestracao, ServicoTriagem
from mediflow_contracts.models import ArmazenamentoOCI, Evento
from test_triage_service import (
    ConfirmadorFake,
    DecisorFake,
    ExtratorFake,
    PersistidorFake,
    documento,
)
from test_triage_persistence_adapter import criar_servico, preparar


def _pipeline(mutar_decisao, *, doc_id="DOC-001"):
    class DecisorAlterado(DecisorFake):
        def decidir(self, extracao, *, entrada, rag, alerta_textual_confirmado):
            saida = super().decidir(
                extracao,
                entrada=entrada,
                rag=rag,
                alerta_textual_confirmado=alerta_textual_confirmado,
            )
            mutar_decisao(saida)
            return saida

    return ServicoTriagem(
        extrator=ExtratorFake(doc_id),
        confirmador=ConfirmadorFake(),
        decisor=DecisorAlterado(),
    )


@pytest.mark.parametrize(
    "modificar",
    [
        lambda r: setattr(r.entrada, "nome_arquivo", "outro.pdf"),
        lambda r: setattr(r.entrada, "canal_origem", "canal-adulterado"),
        lambda r: setattr(r.entrada, "sha256", "b" * 64),
    ],
    ids=["nome-arquivo", "canal-origem", "hash-original"],
)
def test_i1_recusa_mudanca_de_dados_da_entrada(modificar):
    servico = _pipeline(modificar)
    with pytest.raises(FalhaOrquestracao, match="RESULTADO_INCONSISTENTE"):
        servico.executar(documento("DOC-001"), canal_origem="teste")


@pytest.mark.parametrize(
    "modificar",
    [
        lambda r: setattr(r.dados_extraidos.exame, "nome", "Exame fabricado"),
        lambda r: setattr(r.evidencias[0], "trecho_documento", "Evidencia fabricada"),
        lambda r: setattr(r.classificacao, "tipo_documento", "atestado"),
    ],
    ids=["dados-extraidos", "evidencias", "tipo-documental"],
)
def test_i1_recusa_mudanca_da_extracao_original(modificar):
    servico = _pipeline(modificar)
    with pytest.raises(FalhaOrquestracao, match="RESULTADO_INCONSISTENTE"):
        servico.executar(documento("DOC-001"), canal_origem="teste")


def test_i1_decisor_nao_pode_declarar_oci_antecipadamente():
    def declarar_storage(r):
        r.armazenamento_oci = ArmazenamentoOCI(
            status="confirmado",
            bucket="bucket-ficticio",
            chave_original="originais/DOC-001/a.pdf",
            chave_resultado="resultados/DOC-001/a.json",
            chave_historico="historicos/DOC-001/a.json",
        )

    servico = _pipeline(declarar_storage)
    with pytest.raises(FalhaOrquestracao, match="RESULTADO_INCONSISTENTE"):
        servico.executar(documento("DOC-001"), canal_origem="teste")


def test_i1_nao_aceita_r001_disparada_sem_confirmacao_independente():
    def inserir_regra_indevida(r):
        r.decisao_roteamento.regras_disparadas.append("R001")

    servico = _pipeline(inserir_regra_indevida)
    with pytest.raises(FalhaOrquestracao, match="ALERTA_SEM_CONFIRMACAO_INDEPENDENTE"):
        servico.executar(documento("DOC-001"), canal_origem="teste")


def test_i1_alerta_confirmado_exige_r001_principal():
    def rebaixar_regra(r):
        r.decisao_roteamento.regra_principal = "R002"

    servico = _pipeline(rebaixar_regra, doc_id="DOC-002")
    with pytest.raises(FalhaOrquestracao, match="ALERTA_SEM_CONFIRMACAO_INDEPENDENTE"):
        servico.executar(documento("DOC-002", marcador=True), canal_origem="teste")


def test_i1_persistidor_nao_pode_acrescentar_eventos():
    class PersistidorComMutacao(PersistidorFake):
        def persistir(self, resultado):
            saida = super().persistir(resultado)
            saida.eventos.append(Evento(codigo="ALTERADO", descricao="Evento injetado"))
            return saida

    servico = ServicoTriagem(
        extrator=ExtratorFake("DOC-001"),
        confirmador=ConfirmadorFake(),
        decisor=DecisorFake(),
        persistidor=PersistidorComMutacao(),
    )
    with pytest.raises(FalhaOrquestracao, match="PERSISTENCIA_NAO_CONFIRMADA"):
        servico.executar(documento("DOC-001"), canal_origem="teste")


def test_i1_nao_mistura_dois_uploads_do_mesmo_documento():
    fake, storage, recibo_a, original_a = preparar("DOC-001", arquivo_id="a" * 32)
    outro_fake, _, recibo_b, original_b = preparar("DOC-001", arquivo_id="b" * 32)
    fake.objetos.update(outro_fake.objetos)

    saida_a = criar_servico(storage, recibo_a).executar(
        original_a, canal_origem=recibo_a.entrada.canal_origem
    )
    saida_b = criar_servico(storage, recibo_b).executar(
        original_b, canal_origem=recibo_b.entrada.canal_origem
    )

    for saida, original in [(saida_a, original_a), (saida_b, original_b)]:
        assert saida.armazenamento_oci.status == "confirmado"
        assert f"/{original.arquivo_id}/" in saida.armazenamento_oci.chave_resultado
        assert f"/{original.arquivo_id}/" in saida.armazenamento_oci.chave_historico
    assert saida_a.armazenamento_oci.chave_resultado != saida_b.armazenamento_oci.chave_resultado


# Regressões de consistência do I1.


def test_i1_especialidade_nao_pode_ser_inventada_pelo_decisor():
    servico = _pipeline(
        lambda r: setattr(r.classificacao, "especialidade_texto", "Especialidade inventada")
    )
    with pytest.raises(FalhaOrquestracao, match="RESULTADO_INCONSISTENTE"):
        servico.executar(documento("DOC-001"), canal_origem="teste")


def test_i1_regra_principal_deve_estar_em_disparadas():
    servico = _pipeline(
        lambda r: setattr(r.decisao_roteamento, "regras_disparadas", ["R002"]),
        doc_id="DOC-002",
    )
    with pytest.raises(FalhaOrquestracao, match="RESULTADO_INCONSISTENTE"):
        servico.executar(documento("DOC-002", marcador=True), canal_origem="teste")


@pytest.mark.parametrize(
    "destino_incorreto", ["auditoria_autorizacoes", "fila_farmacia_documental"]
)
def test_lacuna_i4_destino_deve_combinar_com_regra_principal(destino_incorreto):
    servico = _pipeline(
        lambda r: setattr(r.decisao_roteamento, "destino_principal", destino_incorreto)
    )
    with pytest.raises(FalhaOrquestracao, match="RESULTADO_INCONSISTENTE"):
        servico.executar(documento("DOC-001"), canal_origem="teste")
