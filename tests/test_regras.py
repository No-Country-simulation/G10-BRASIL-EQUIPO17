import json
from pathlib import Path
import yaml
import pytest
from mediflow_contracts.models import ExtracaoIA
from mediflow_contracts.routing import escolher_regra, gerar_exemplo_de_contrato

ROOT=Path(__file__).resolve().parents[1]

def leitura_doc(doc_id):
    return ExtracaoIA.model_validate_json((ROOT/'exemplos'/f'{doc_id}_extracao_ia.json').read_text(encoding='utf-8'))

def test_yaml_precedencia_integra():
    r=yaml.safe_load((ROOT/'rules/roteamento.yaml').read_text(encoding='utf-8'))
    assert r['precedencia']==['R001','R002','R003','R004','R005','R006']
    assert set(r['precedencia'])=={x['id'] for x in r['regras']}
    assert len({x['condicao'] for x in r['regras']}) == 6
    v=yaml.safe_load((ROOT/'rules/validacao.yaml').read_text(encoding='utf-8'))
    assert len(v['validacoes'])==4

@pytest.mark.parametrize('doc,urgente,esperada',[
 ('DOC-001',False,'R005'),('DOC-002',True,'R001'),('DOC-005',False,'R002')
])
def test_regras_com_amostras(doc,urgente,esperada):
    regra,disparadas,*_=escolher_regra(leitura_doc(doc),alerta_textual_confirmado=urgente)
    assert regra['id']==esperada
    assert disparadas[0]==esperada


def test_tipo_desconhecido_vai_fallback():
    data=leitura_doc('DOC-001').model_dump()
    data['tipo_documento']='outro_desconhecido'
    data['dados_extraidos']['paciente']={'nome':'Marina','nome_status':'legivel'}
    regra,*_=escolher_regra(ExtracaoIA.model_validate(data),alerta_textual_confirmado=False)
    assert regra['id']=='R006'


def test_laudo_sem_conclusao_para_auditoria():
    data=leitura_doc('DOC-002').model_dump()
    data['dados_extraidos']['exame']['conclusao']=None
    regra,disparadas,*_=escolher_regra(ExtracaoIA.model_validate(data),alerta_textual_confirmado=False)
    assert regra['id']=='R002'


def test_ausencia_paciente_para_auditoria():
    data=leitura_doc('DOC-001').model_dump()
    data['dados_extraidos']['paciente']={'nome':None,'nome_status':'ausente'}
    regra,disparadas,*_=escolher_regra(ExtracaoIA.model_validate(data),alerta_textual_confirmado=False)
    assert regra['id']=='R002'
