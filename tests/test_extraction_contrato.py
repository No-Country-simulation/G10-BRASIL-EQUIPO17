import pytest
from pydantic import ValidationError
from mediflow_contracts.models import ExtracaoIA, DadosExtraidos, Medicamento


def test_dosagem_ilegivel_sem_valor_e_aceita():
    extracao = ExtracaoIA(
        documento_id="DOC-001",
        tipo_documento="receituario",
        dados_extraidos=DadosExtraidos(
            medicamentos=[Medicamento(nome="Medicamento A", dosagem_status="ilegivel")]
        ),
    )
    assert extracao.dados_extraidos.medicamentos[0].dosagem_texto is None


def test_dosagem_ilegivel_com_valor_inventado_e_rejeitada():
    with pytest.raises(ValidationError):
        Medicamento(nome="Medicamento A", dosagem_status="ilegivel", dosagem_texto="10 mg")
