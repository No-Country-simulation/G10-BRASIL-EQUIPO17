# MediFlow — Dia 3 | Monorepo executável

**Hackathon ONE G10 — Projeto educacional de triagem documental**  
**Planejamento:** 6 integrantes, 5 semanas, Dia 3 de 25.  
**Contrato:** `v0.1`, herdado do Dia 2; regras R001–R006, incluindo R004.

> Uso exclusivo com dados sintéticos. Não diagnostica, não recomenda condutas médicas e não está pronto para produção.

## Preparar no Windows (PowerShell)

Pré-requisitos: [Python 3.12](https://www.python.org/downloads/) e Git.

```powershell
cd MediFlow_Dia03
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn mediflow.api.app:app --reload
```

Abra `http://127.0.0.1:8000/docs` e teste `GET /health`.
A rota `POST /v1/triagens/texto` apenas valida o JSON: uma entrada correta recebe HTTP **501** até implementarmos a ingestão no Dia 5. Entradas inválidas recebem **422**.

## Preparar no Linux/macOS
```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/python -m uvicorn mediflow.api.app:app --reload
```

## Por onde começar
- `docs/01_arquitetura_monorepo.md` — módulos e suas responsabilidades.
- `docs/02_git_colaboracao.md` — branches e PRs para a equipe.
- `docs/03_plano_dia03.md` — critérios de aceite e divisão do dia.
- `docs/dia02/01_contrato_api.md` — especificação herdada da API.
- `schemas/`, `rules/`, `exemplos/` — baseline Dia 2.
- `.github/workflows/ci.yml` — CI preparada para GitHub Actions (Python 3.12 e 3.13).

## O que **não** foi implementado
Leitura real de PDF/imagem, LLM, RAG, grafo LangGraph, upload Oracle, autenticação, Streamlit e deploy remoto.
O pacote **não cria nem publica** um repositório na conta GitHub do usuário.

## Ordem das próximas entregas
Dia 4: bucket OCI e upload real. Dia 5: endpoint de ingestão e catálogo de fontes.
Sem publicar no GitHub, não há evidência de execução remota da CI.
