import json
from pathlib import Path

import pytest


RAIZ = Path(__file__).resolve().parents[1]
ARQUIVOS = [
    RAIZ / "exemplos/DOC-005_extracao_ia.json",
    RAIZ / "exemplos/DOC-005_resultado.json",
]


@pytest.mark.parametrize("caminho", ARQUIVOS)
def test_doc005_campos_legiveis_e_dosagem_ilegivel(caminho):
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    extraidos = dados["dados_extraidos"]

    assert extraidos["profissional"]["nome"] == "Dr. André Lima Exemplo"
    assert extraidos["profissional"]["crm_texto"] == "CRM-XX 000005"
    assert extraidos["data_emissao"] == "2026-10-20"

    medicamento = extraidos["medicamentos"][0]
    assert medicamento["nome"] == "Medicamento Alfa (fictício)"
    assert medicamento["dosagem_texto"] is None
    assert medicamento["dosagem_status"] == "ilegivel"

    evidencias = {
        evidencia["campo"]: evidencia
        for evidencia in dados["evidencias"]
    }

    esperadas = {
        "profissional.nome": "Dr. André Lima Exemplo",
        "profissional.crm_texto": "CRM-XX 000005",
        "data_emissao": "20/10/2026",
    }

    for campo, trecho in esperadas.items():
        assert campo in evidencias
        assert evidencias[campo]["trecho_documento"] == trecho
        assert evidencias[campo]["pagina"] == 1
        assert evidencias[campo]["origem"] == "documento"


def test_doc005_resultado_preserva_encaminhamento_r002():
    caminho = RAIZ / "exemplos/DOC-005_resultado.json"
    dados = json.loads(caminho.read_text(encoding="utf-8"))

    assert dados["status"] == "aguardando_auditoria"
    decisao = dados["decisao_roteamento"]
    assert decisao["destino_principal"] == "auditoria_humana"
    assert decisao["requer_revisao_humana"] is True
    assert decisao["regra_principal"] == "R002"
    assert "R002" in decisao["regras_disparadas"]
