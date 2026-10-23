# Responsabilidades e critérios — Dia 2

| Pessoa | Compromisso | Evidência no pacote |
|---|---|---|
| I1 (principal) | Definir contratos, endpoints e modelos Pydantic | `models.py`, `schemas/`, `docs/01_contrato_api.md` |
| I4 (principal) | Definir precedência, regras YAML, destinos, transições | `rules/`, `routing.py`, diagrama |
| I2 (apoio) | Conferir campos extraídos, nulidade e exemplos dos três documentos | `exemplos/*_extracao_ia.json` |
| I3 (apoio) | Definir rastreabilidade RAG e comportamento de fallback | campos `rag`, descrição do grafo |
| I5 (revisão) | Verificar contrato para OCI e estados de falha | `ArmazenamentoOCI`, docs |
| I6 (revisão) | Conferir critérios e implementar testes contratuais | `tests/` |

## Critérios de pronto
1. 3 JSON Schemas gerados de uma única fonte canônica Pydantic.
2. 3 pares de extrações/resultados válidos comparados com o gabarito do Dia 1.
3. Regras em YAML carregáveis e destinos compatíveis com categorias do Dia 1.
4. Exceção `urgencia + ambiguidade` preserva prioridade e conserva a anotação de ambiguidade.
5. Uma dose `ilegivel` não pode conter valor de texto afirmado.
6. Erro de persistência não pode se declarar `confirmado`.
7. Diagrama Mermaid versionável, com fallback e OCI.
8. Avaliação humana para urgência/ambiguidade e sem decisões clínicas automáticas.

## Critérios ainda dependentes do grupo
- Revisão de contratos pelos 6 integrantes (não presumir consenso técnico).
- Seleção real de provedor LLM e credenciais OCI; não são parte desta entrega.
- Aprovação de tamanhos máximos de arquivo/páginas e política de autenticação.
