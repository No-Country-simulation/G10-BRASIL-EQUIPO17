# Mapa de módulos, responsabilidades e branches sugeridas

**Referência vigente:** [CONTRIBUTING.md](../CONTRIBUTING.md). A nomenclatura descreve o objetivo da entrega, independentemente da semana em que ela for realizada.

| Integrante | Área | Módulos principais | Branches possíveis |
|---|---|---|---|
| I1 | Arquitetura e API | `src/mediflow/api/`, contratos, integração | `feat/api-document-upload`, `feat/api-triage-processing` |
| I2 | Leitura e extração por IA | `src/mediflow/extraction/`, `ingestion/` | `feat/ai-pdf-processing`, `feat/ai-document-extraction` |
| I3 | Conhecimento e RAG | `src/mediflow/rag/`, documentos de referência | `feat/rag-knowledge-base`, `feat/rag-knowledge-retrieval` |
| I4 | Regras e agente | `rules/`, `src/mediflow/agents/` | `feat/rules-routing-engine`, `feat/agent-langgraph-workflow` |
| I5 | Nuvem e segurança | `src/mediflow/storage/`, integração Oracle | `feat/oci-object-storage`, `feat/oci-audit-persistence` |
| I6 | Interface e qualidade | `src/mediflow/ui/`, `tests/` | `feat/ui-document-dashboard`, `feat/ui-human-review`, `test/e2e-triage-scenarios` |

**Aviso:** são exemplos de branches **a criar**, não nomes de branches já disponíveis.

## Como organizar o backlog

1. Abrir Issue/tarefa pelo objetivo funcional, com responsáveis, riscos e critérios de aceite.
2. Dividir tarefas grandes em incrementos testáveis e, se possível, PRs pequenos.
3. Criar branch `tipo/area-funcionalidade` a partir da `develop` atualizada.
4. Executar testes e abrir PR direcionado à `develop`.
5. Documentar mudanças relevantes e evidências de teste no PR.
6. Integrar à `main` apenas por promoção estável e revisão da equipe.

## Diretrizes de compatibilidade

- Código em `src/mediflow_contracts/models.py` é a origem dos contratos; **não** editar `schemas/*.schema.json` manualmente.
- As regras R001–R006 são preservadas; mudanças exigem testes e aprovação.
- As saídas do RAG oferecem contexto, mas não substituem regras determinísticas nem supervisão humana.
- Nenhuma integração clínica real ou decisão médica deve ser apresentada como concluída sem evidência de execução.

## Material histórico

`baseline_dia1/`, `docs/dia02/` e relatórios ligados ao Dia 3 são snapshots de planejamento e validação; seus nomes foram preservados para não quebrar referências e testes existentes. A **regra de nomenclatura se aplica às branches novas**, não aos registros históricos ou tags já emitidas.
