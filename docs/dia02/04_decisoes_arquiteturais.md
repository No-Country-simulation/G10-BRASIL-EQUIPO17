# Registro de decisões técnicas — ADRs em elaboração

- **ADR-001 (proposta v0.1):** modelos Pydantic como fonte; JSON Schema como artefato exportado, utilizado por clientes não Python.
- **ADR-002:** API separa envio JSON de texto de multipart para anexos binários.
- **ADR-003:** LangGraph como futuro orquestrador; regras executadas por funções determinísticas.
- **ADR-004:** prioridade de urgência depende de marcador efetivamente verificado no documento; regras do protótipo não configuram avaliação clínica.
- **ADR-005:** RAG opcional, não autoritativo e com fontes versionadas; indisponibilidade não elimina alerta.
- **ADR-006:** OCI só pode retornar `confirmado` após sucessos verificáveis; não persistimos histórias falsas de armazenamento em fixtures.
- **ADR-007:** `indicador_qualidade` não representa confiança probabilística, não inventar números.
- **ADR-008:** preservar categorias/destinos/IDs de regras do Dia 1.

**Status:** proposta técnica do Integrante Universal para revisão dos integrantes I1–I6. Não confundir validação de schemas local com testes de integração executados.

## Referências de implementação (documentação oficial)
- FastAPI nested models: https://fastapi.tiangolo.com/tutorial/body-nested-models/
- FastAPI response models: https://fastapi.tiangolo.com/tutorial/response-model/
- LangGraph `add_conditional_edges`: https://reference.langchain.com/python/langgraph/graph/state/StateGraph/add_conditional_edges
- Documento do hackathon fornecido pela equipe: `MediaFlow_Hackathon.pdf`, páginas 1–6.
