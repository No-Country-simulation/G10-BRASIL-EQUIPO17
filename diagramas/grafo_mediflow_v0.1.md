# MediFlow — Grafo de decisão v0.1 (revisão visual de R004)

Este fluxo contém **as seis regras R001, R002, R003, R004, R005 e R006 individualizadas**. A regra R004 — receituário completo para **fila documental da farmácia** — não está mais implícita no bloco `R003–R005`.

## Precedência e comportamento

1. **R001** — marcador explícito de possível urgência confirmado → fila prioritária de avaliação humana.
2. **R002** — ambiguidade crítica sem marcador prioritário → auditoria humana.
3. **R003** — solicitação de exame documentalmente completa → auditoria de autorizações.
4. **R004** — receituário documentalmente completo → fila documental da farmácia, sem dispensação automática.
5. **R005** — demais documentos de rotina documentalmente completos → prontuário documental.
6. **R006** — ausência de condições para os destinos anteriores → auditoria humana (fallback).

Se um documento disparar R001 e R002 simultaneamente, **R001 vence**, mas ambas devem constar em `regras_disparadas` conforme contrato v0.1.

Quando o RAG falhar ou não encontrar fontes, as regras determinísticas continuam operando e o status da consulta é registrado.

Falhas técnicas não são tratadas como roteamento de rotina, e o OCI só pode ser declarado confirmado após evidência da gravação.

## Visualizações

- `grafo_mediflow_v0.1.png`: imagem revisada.
- `grafo_mediflow_v0.1.svg`: imagem vetorial, ideal para zoom e apresentação.
- `grafo_mediflow_v0.1.mmd`: fonte Mermaid editável e legível em editores compatíveis.
- `grafo_mediflow_v0.1.dot`: fonte Graphviz exata da renderização PNG/SVG.

## Contrato de estado planejado

- `documento_id`, `entrada`, `conteudo_normalizado`, `extracao`, `validacao`, `rag`, `decisao`, `armazenamento`, `erros`, `eventos`.
- Campos críticos somente são aceitos com evidência do documento, nunca de uma referência recuperada pelo RAG.
- Para evitar exposição de dados sensíveis, não registrar texto integral do documento em logs.

**Escopo:** desenho de implementação futura; nenhum serviço LangGraph, LLM ou OCI é executado por este diagrama.
