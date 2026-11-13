"""H12: matriz de erros seguros da API I1 (somente fakes, sem rede).

Executa sobre o router de processamento isolado; NAO publica /processar.
Os dados dos testes sao sinteticos e os marcadores de segredo sao ficticios.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mediflow.api.app import app as app_develop
from mediflow.api.triage_processing import obter_servico_triagem
from mediflow.api.triage_service import FalhaOrquestracao
from mediflow_contracts.models import ResultadoTriagem
from test_api_triage_processing import api, enviar, processar

RAIZ = Path(__file__).resolve().parents[1]
SEGREDO_SINTETICO = "OCI_API_KEY=CHAVE_FICTICIA_H12_NAO_EXIBIR"


def _validar_erro(resposta, http: int, codigo: str) -> None:
    assert resposta.status_code == http, resposta.text
    corpo = resposta.json()
    assert set(corpo) == {"detail"}
    detalhe = corpo["detail"]
    assert set(detalhe) == {"codigo", "mensagem"}
    assert detalhe["codigo"] == codigo
    assert isinstance(detalhe["mensagem"], str) and detalhe["mensagem"]
    assert SEGREDO_SINTETICO not in resposta.text
    assert "SEGREDO_QUE_NAO_DEVE_APARECER" not in resposta.text


@pytest.mark.parametrize(
    "etapa,codigo",
    [
        ("entrada", "ENTRADA_PROCESSAMENTO_INVALIDA"),
        ("extracao", "EXTRACAO_INDISPONIVEL"),
        ("alerta", "CONFIRMACAO_INDISPONIVEL"),
        ("decisao", "DECISAO_INDISPONIVEL"),
        ("persistencia", "PERSISTENCIA_INDISPONIVEL"),
        ("etapa_nao_mapeada", "PROCESSAMENTO_INDISPONIVEL"),
    ],
)
def test_h12_mapeamento_de_falhas_do_servico_nao_expoe_segredos(api, etapa, codigo):
    recibo = enviar(api)
    api.servico.falha = FalhaOrquestracao(SEGREDO_SINTETICO, etapa)

    resposta = processar(api, recibo)

    _validar_erro(resposta, 502, codigo)
    assert len(api.servico.chamadas) == 1


@pytest.mark.parametrize("tipo", [RuntimeError, OSError, ValueError])
def test_h12_excecao_inesperada_e_sanitizada(api, tipo):
    recibo = enviar(api)
    api.servico.falha = tipo(SEGREDO_SINTETICO)

    resposta = processar(api, recibo)

    _validar_erro(resposta, 502, "PROCESSAMENTO_INDISPONIVEL")
    assert len(api.servico.chamadas) == 1


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("documento_id", "DOC-OUTRO"),
        ("entrada.tipo_entrada", "png"),
        ("entrada.canal_origem", "canal-ficticio-divergente"),
        ("entrada.nome_arquivo", "outro-arquivo.pdf"),
        ("entrada.sha256", "a" * 64),
        ("status", "processando"),
    ],
)
def test_h12_resultado_divergente_rejeitado_com_502(api, campo, valor):
    recibo = enviar(api)
    dados = json.loads(
        (RAIZ / "exemplos/DOC-001_resultado.json").read_text(encoding="utf-8")
    )
    if "." in campo:
        grupo, nome = campo.split(".")
        dados[grupo][nome] = valor
    else:
        dados[campo] = valor
    # Contrato valido, mas nao pertence ao documento/execucao solicitados.
    api.servico.retorno_forcado = ResultadoTriagem.model_validate(dados)

    resposta = processar(api, recibo)

    _validar_erro(resposta, 502, "RESULTADO_INCONSISTENTE")
    assert len(api.servico.chamadas) == 1


def test_h12_manifesto_indisponivel_retorna_502_sem_extracao(api):
    recibo = enviar(api)
    api.storage.fail_prefix = "metadados/"

    resposta = processar(api, recibo)

    _validar_erro(resposta, 502, "FALHA_CONSULTA_METADADOS")
    assert api.servico.chamadas == []


def test_h12_manifesto_inexistente_retorna_404_sem_extracao(api):
    recibo = enviar(api)
    del api.storage.objetos[recibo["registro_metadados"]["chave_metadados"]]

    resposta = processar(api, recibo)

    _validar_erro(resposta, 404, "REGISTRO_NAO_ENCONTRADO")
    assert api.servico.chamadas == []


def test_h12_original_indisponivel_retorna_502_sem_extracao(api):
    recibo = enviar(api)
    del api.storage.objetos[recibo["armazenamento_original"]["chave_original"]]

    resposta = processar(api, recibo)

    _validar_erro(resposta, 502, "ORIGINAL_INDISPONIVEL")
    assert api.servico.chamadas == []


def test_h12_sem_servico_configurado_retorna_503_antes_de_ler_oci(api):
    recibo = enviar(api)
    api.app.dependency_overrides.pop(obter_servico_triagem)
    api.storage.reads.clear()

    resposta = processar(api, recibo)

    _validar_erro(resposta, 503, "TRIAGEM_NAO_CONFIGURADA")
    assert api.storage.reads == []
    assert api.servico.chamadas == []


def test_h12_saida_nao_compativel_com_o_contrato_retorna_502(api):
    recibo = enviar(api)
    api.servico.retorno_forcado = {"status": "processado", "segredo": SEGREDO_SINTETICO}

    resposta = processar(api, recibo)

    _validar_erro(resposta, 502, "PROCESSAMENTO_INDISPONIVEL")
    assert len(api.servico.chamadas) == 1


def test_h12_endpoint_nao_esta_publicado_no_app_principal():
    rota = "/v1/triagens/arquivos/{documento_id}/{arquivo_id}/processar"
    assert rota not in app_develop.openapi()["paths"]
