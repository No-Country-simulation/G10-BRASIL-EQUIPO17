# Execução do Dia 3 — responsabilidades e aceite

| Bloco | Principal | Apoio | Evidência |
|---|---|---|---|
| Monorepo e pacote instalável | I1 | I5 | `pyproject.toml`, importações e testes |
| Branches e fluxo de PR | I1 | I6 | `main`, `develop`, instruções e modelo PR |
| CI básica | I5 | I1 e I6 | `.github/workflows/ci.yml` (pendente execução remota) |
| Ambiente e segurança inicial | I5 | I1 | `.python-version`, `.env.example`, `.gitignore` |
| FastAPI mínima | I1 | I6 | `/health`, OpenAPI e endpoint 501 deliberado |
| Regressão Dia 2 | I6 | I2, I4 | 25 testes anteriores + novos testes |

## Critérios de aceite para encerrar o Dia 3
1. Projeto instalável em Python compatível, sem API externa.
2. Testes locais de Dia 2 e de Dia 3 aprovados.
3. Regras R001–R006 preservadas e diagramas corrigidos incluídos.
4. Fluxo de branches documentado e branches locais `main`, `develop` existentes.
5. Workflow de GitHub Actions versionado, **mas execução remota só após publicar**.
6. `GET /health` e a documentação da API disponíveis em execução local.
7. `POST /v1/triagens/texto` valida entrada e retorna 501 em vez de simular processamento.

## Próximo — Dia 4
- OCI Always Free: bucket privado, credenciais locais seguras e teste real de upload (somente dados sintéticos).
- Sem credenciais do usuário, esse passo **não** deve ser considerado concluído.
