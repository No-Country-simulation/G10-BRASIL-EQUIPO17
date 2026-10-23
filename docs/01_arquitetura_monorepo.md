# Arquitetura do monorepo — Dia 3

## Limites de módulos

- `src/mediflow/api`: FastAPI e validação na borda — I1.
- `src/mediflow/ingestion`: leitura e normalização PDF/imagem/texto — I2 (Semana 2).
- `src/mediflow/agents`: LangGraph e conexão dos módulos — I4 (Semana 3).
- `src/mediflow/rag`: indexação/recuperação e citações — I3 (Semana 2/3).
- `src/mediflow/rules`: execução das regras de roteamento — I4 (Semana 2).
- `src/mediflow/storage`: acesso ao OCI Object Storage — I5 (Dia 4/5).
- `src/mediflow/ui`: interface Streamlit — I6 (Semana 4).
- `src/mediflow_contracts`: código canônico Pydantic **herdado do Dia 2**, sem alterações funcionais.
- `rules/*.yaml`: catálogo R001–R006 **herdado do Dia 2**.
- `schemas/*.json`: derivados do Pydantic; não editar manualmente.
- `tests`: 25 testes do Dia 2 e novos testes de infraestrutura/API do Dia 3.

## O que existe hoje
- API inicial `/health` e stub `/v1/triagens/texto` com validação Pydantic (retorno HTTP 501).
- Regras documentais e fixtures já validadas no Dia 2.
- Arquivos iniciais de CI e estratégia de branches.

## O que ainda não existe
- Classificação/extracao por LLM; ingestão real de anexos/PDF; RAG executável; LangGraph compilado; OCI;
  autenticação/autorização; interface Streamlit; deploy em nuvem.

## Contratos de segurança
- Apenas dados sintéticos no repositório.
- Um endpoint `health` não significa sucesso dos serviços dependentes.
- `OCI.status=pendente` permanece até haver comprovação de gravação.
- Marcadores de urgência precisam de evidência documental verificada independentemente do texto inferido pela LLM.
- RAG nunca rebaixa prioridade e não constitui fonte de evidência do conteúdo recebido.
