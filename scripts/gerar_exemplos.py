"""Cria exemplos SINTETICOS (nao executa inferencia real, OCI ou RAG)."""
from pathlib import Path
import json,sys
RAIZ=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(RAIZ/'src'))
from mediflow_contracts.models import ExtracaoIA
from mediflow_contracts.routing import gerar_exemplo_de_contrato

casos = {
'DOC-001': {'entrada':'pdf', 'alerta':False, 'extracao':{
 'contrato_versao':'0.1','documento_id':'DOC-001','tipo_documento':'laudo_laboratorial',
 'dados_extraidos':{
  'paciente':{'nome':'Marina Lacerda Fictícia','nome_status':'legivel','identificador':'PF-0001','idade':38},
  'profissional':{'nome':'Dra. Elisa Monteiro Exemplo','crm_texto':'CRM-XX 000001'},
  'exame':{'nome':'Hemograma completo','conclusao':'Resultados descritos para acompanhamento de rotina. Documento sem declaração de urgência.',
   'resultados':[{'parametro':'Hemoglobina','valor_texto':'13,4','unidade':'g/dL'},
                {'parametro':'Leucócitos','valor_texto':'6.800','unidade':'/mm3'},
                {'parametro':'Plaquetas','valor_texto':'245.000','unidade':'/mm3'}]},
  'data_emissao':'2026-10-18'
 },
 'evidencias':[
  {'campo':'paciente.nome','trecho_documento':'Marina Lacerda Fictícia | 38 anos | ID interno: PF-0001','pagina':1},
  {'campo':'exame.nome','trecho_documento':'Hemograma completo - material: sangue total','pagina':1},
  {'campo':'data_emissao','trecho_documento':'Emissão: 18/10/2026','pagina':1}
 ]
}},
'DOC-002': {'entrada':'pdf','alerta':True,'extracao':{
 'contrato_versao':'0.1','documento_id':'DOC-002','tipo_documento':'laudo_imagem',
 'dados_extraidos':{
  'paciente':{'nome':'Carlos Almeida Exemplo','nome_status':'legivel','idade':52},
  'profissional':{'nome':'Dra. Renata Silveira Exemplo','crm_texto':'CRM-XX 000002'},
  'exame':{'nome':'Angiotomografia de tórax com contraste','achados':'Falha de enchimento em ramo arterial pulmonar.',
          'conclusao':'Achados descritos como compatíveis com tromboembolismo pulmonar agudo.'},
  'data_emissao':'2026-10-19'
 },
 'sinais_documentais':{'marcador_urgencia_explicito':True,'transcricao_marcador_urgencia':'ACHADO CRÍTICO - URGENTE'},
 'evidencias':[
  {'campo':'paciente.nome','trecho_documento':'Carlos Almeida Exemplo | 52 anos','pagina':1},
  {'campo':'exame.conclusao','trecho_documento':'Achados descritos como compatíveis com tromboembolismo pulmonar agudo.','pagina':1},
  {'campo':'sinais_documentais.marcador_urgencia_explicito','trecho_documento':'ACHADO CRÍTICO - URGENTE. Comunicar equipe assistencial imediatamente','pagina':1}
 ]
}},
'DOC-005': {'entrada':'png','alerta':False,'extracao':{
 'contrato_versao':'0.1','documento_id':'DOC-005','tipo_documento':'receituario',
 'dados_extraidos':{
  'paciente':{'nome':'Fernanda Oliveira Exemplo','nome_status':'legivel'},
  'medicamentos':[{'nome':'Medicamento Alfa (fictício)','dosagem_texto':None,'dosagem_status':'ilegivel'}]
 },
 'evidencias':[
  {'campo':'paciente.nome','trecho_documento':'Fernanda Oliveira Exemplo','pagina':1},
  {'campo':'medicamentos[0].nome','trecho_documento':'Medicamento Alfa (fictício)','pagina':1}
 ]
}}
}

for doc_id, conf in casos.items():
    extracao=ExtracaoIA.model_validate(conf['extracao'])
    out=gerar_exemplo_de_contrato(extracao, formato=conf['entrada'], alerta_textual_confirmado=conf['alerta'])
    (RAIZ/'exemplos'/f'{doc_id}_extracao_ia.json').write_text(json.dumps(extracao.model_dump(mode='json'),indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (RAIZ/'exemplos'/f'{doc_id}_resultado.json').write_text(json.dumps(out.model_dump(mode='json'),indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

entrada = {
 'contrato_versao':'0.1','documento_id':'DOC-TEXTO-001','canal_origem':'teste_sintetico',
 'documento_texto':'ATESTADO FICTÍCIO: Paciente Exemplo, emissão em 20/10/2026. Documento apenas para teste.'
}
(RAIZ/'exemplos'/'entrada_texto.json').write_text(json.dumps(entrada,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('7 arquivos de exemplo gerados; nenhuma LLM/API/OCI executada')
