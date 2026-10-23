# Relatório de validação — Dia 3

**Ambiente observado:** Python 3.13.5, dependências de teste já presentes no ambiente.

## Execução local concluída
- Instalação editável: `python -m pip install --no-deps --no-build-isolation -e .` — **aprovada**.
- Sintaxe: `python -m compileall -q src scripts tests` — **aprovada**.
- Testes: `python -m pytest -q` — **34 aprovados, 0 falhas**.
- FastAPI: testes para `/health`, `/openapi.json`, 422 em entrada inválida e 501 em entrada válida.
- Dia 2: 25 testes de contratos/regras herdados, com R004 preservada.

## Limitações e próximos testes
- Essa execução **não** instalou as dependências diretamente da internet; usou pacotes já presentes no ambiente.
- Python 3.12 está declarado como versão de referência, mas a CI hospedada em 3.12/3.13 ainda precisa ser executada no GitHub.
- Integração GitHub Actions: arquivo YAML validado localmente; **workflow não rodou remotamente**.
- Integrações LLM, LangGraph, RAG e OCI não foram executadas nem simuladas como concluídas.
- Ainda não existe processamento real de texto, PDF ou imagem.
