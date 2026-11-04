
import json

import pytest
from pydantic import ValidationError

from mediflow.extraction.extractor import (
    preparar_entrada,
    validar_extracao,
)
from mediflow_contracts.models import EntradaTexto


def test_validar_extracao_valida():
    resposta = {
        "documento_id": "DOC-001",
        "tipo_documento": "laudo_laboratorial",
        "dados_extraidos": {},
    }

    resultado = validar_extracao(
        "DOC-001",
        json.dumps(resposta),
    )

    assert resultado.documento_id == "DOC-001"
    assert resultado.tipo_documento == "laudo_laboratorial"


def test_rejeitar_json_invalido():
    with pytest.raises(ValueError, match="JSON válido"):
        validar_extracao("DOC-001", "{json inválido")


def test_rejeitar_documento_id_diferente():
    resposta = {
        "documento_id": "DOC-002",
        "tipo_documento": "receituario",
        "dados_extraidos": {},
    }

    with pytest.raises(ValueError, match="não corresponde"):
        validar_extracao("DOC-001", json.dumps(resposta))


def test_preparar_entrada():
    entrada = EntradaTexto(
        documento_id="DOC-001",
        canal_origem="teste",
        documento_texto="Documento fictício para teste.",
    )

    preparada = preparar_entrada(entrada)

    assert preparada["documento_id"] == "DOC-001"
    assert preparada["documento_texto"] == "Documento fictício para teste."


def test_rejeitar_json_que_nao_seja_objeto():
    with pytest.raises(ValueError, match="objeto JSON"):
        validar_extracao("DOC-001", '["não é um objeto"]')


def test_rejeitar_campo_desconhecido():
    resposta = {
        "documento_id": "DOC-001",
        "tipo_documento": "laudo_laboratorial",
        "dados_extraidos": {},
        "campo_inventado": "valor",
    }

    with pytest.raises(ValidationError):
        validar_extracao("DOC-001", json.dumps(resposta))


def criar_resposta_com_evidencia(pagina, trecho):
    return {
        "documento_id": "DOC-001",
        "tipo_documento": "laudo_laboratorial",
        "dados_extraidos": {},
        "evidencias": [
            {
                "campo": "descricao_documento",
                "trecho_documento": trecho,
                "pagina": pagina,
                "origem": "documento",
            }
        ],
    }


def test_validar_evidencia_com_pagina_e_trecho_corretos():
    texto = (
        "[Página 1]\n"
        "Resultado do exame: hemoglobina 13 g/dL.\n\n"
        "[Página 2]\n"
        "Conclusão do documento fictício."
    )

    resposta = criar_resposta_com_evidencia(
        1,
        "Resultado do exame: hemoglobina 13 g/dL.",
    )

    resultado = validar_extracao(
        "DOC-001",
        json.dumps(resposta),
        documento_texto=texto,
    )

    assert resultado.evidencias[0].pagina == 1


def test_rejeitar_evidencia_com_pagina_inexistente():
    texto = (
        "[Página 1]\n"
        "Resultado do exame: hemoglobina 13 g/dL."
    )

    resposta = criar_resposta_com_evidencia(
        2,
        "Resultado do exame: hemoglobina 13 g/dL.",
    )

    with pytest.raises(ValueError, match="página inexistente"):
        validar_extracao(
            "DOC-001",
            json.dumps(resposta),
            documento_texto=texto,
        )


def test_rejeitar_evidencia_com_trecho_incorreto():
    texto = (
        "[Página 1]\n"
        "Resultado do exame: hemoglobina 13 g/dL."
    )

    resposta = criar_resposta_com_evidencia(
        1,
        "Resultado do exame: glicose 100 mg/dL.",
    )

    with pytest.raises(ValueError, match="trecho da evidência"):
        validar_extracao(
            "DOC-001",
            json.dumps(resposta),
            documento_texto=texto,
        )