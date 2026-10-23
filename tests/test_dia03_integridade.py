"""Garante que contrato e roteamento R001-R006 do Dia 2 continuam presentes."""
from pathlib import Path
import json
import yaml

BASE = Path(__file__).resolve().parents[1]


def test_seis_regras_e_precedencia():
    doc = yaml.safe_load((BASE/'rules'/'roteamento.yaml').read_text(encoding='utf-8'))
    assert doc['precedencia'] == ['R001','R002','R003','R004','R005','R006']
    assert [r['id'] for r in doc['regras']] == doc['precedencia']
    r004 = next(r for r in doc['regras'] if r['id'] == 'R004')
    assert r004['destino'] == 'fila_farmacia_documental'


def test_sete_categorias_preservadas():
    dados = json.loads((BASE/'baseline_dia1'/'categorias.json').read_text(encoding='utf-8'))
    assert len(dados['categorias']) == 7


def test_exemplos_sinteticos_presentes():
    for caminho in [
        'amostras/pdf/DOC-001_laudo_laboratorial_rotina.pdf',
        'amostras/pdf/DOC-002_laudo_imagem_alerta.pdf',
        'amostras/imagens/DOC-005_receita_ilegivel.png',
    ]:
        p = BASE / caminho
        assert p.is_file() and p.stat().st_size > 100
