"""Smoke tests da API inicial; nao testam inferencia/OCI."""
from fastapi.testclient import TestClient
from mediflow.api.app import app

client = TestClient(app)


def test_health_nao_afirma_ia_oci():
    res = client.get('/health')
    assert res.status_code == 200
    assert res.json() == {'status': 'ok', 'servico': 'mediflow', 'modo': 'esqueleto_dia03', 'contrato_versao': '0.1'}


def test_openapi_disponivel():
    res = client.get('/openapi.json')
    assert res.status_code == 200
    caminhos = res.json()['paths']
    assert '/health' in caminhos
    assert '/v1/triagens/texto' in caminhos


def test_entrada_texto_valida_retorna_501_e_nao_simula_sucesso():
    payload = {
        'contrato_versao': '0.1', 'documento_id': 'DOC-TEXTO-001',
        'canal_origem': 'teste_sintetico', 'documento_texto': 'Teste ficticio.'
    }
    res = client.post('/v1/triagens/texto', json=payload)
    assert res.status_code == 501
    assert res.json()['detail']['codigo'] == 'TRIAGEM_NAO_IMPLEMENTADA'


def test_entrada_texto_invalida_retorna_422():
    res = client.post('/v1/triagens/texto', json={
        'documento_id': 'nao valido!', 'canal_origem': 'teste', 'documento_texto': 'OK'
    })
    assert res.status_code == 422


def test_entrada_nao_permite_campos_desconhecidos():
    res = client.post('/v1/triagens/texto', json={
        'documento_id':'DOC-TESTE-10', 'canal_origem':'teste',
        'documento_texto':'FICTICIO', 'diagnostico_inventado':'sim'
    })
    assert res.status_code == 422


def test_versao_de_contrato_incompativel_e_rejeitada():
    res = client.post('/v1/triagens/texto', json={
        'contrato_versao':'9.9', 'documento_id':'DOC-TESTE-10',
        'canal_origem':'teste', 'documento_texto':'FICTICIO'
    })
    assert res.status_code == 422
