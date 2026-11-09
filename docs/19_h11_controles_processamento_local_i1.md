# MediFlow — H11: controles de acesso local ao endpoint de processamento (I1)

**Estado:** controles H11 aprovados com simulação local; CI pendente. Integração definitiva do endpoint ainda não realizada. 
**Escopo:** testes com dados sintéticos e FakeOCI/serviço simulado, sem credenciais ou chamadas reais a Gemini, LangGraph ou OCI.

## 1. Objetivo

Validar que `POST /v1/triagens/arquivos/{documento_id}/{arquivo_id}/processar` continua **não publicado** na aplicação FastAPI principal e, quando o router é montado explicitamente numa aplicação isolada de teste, permanece bloqueado por padrão.

Este incremento **não conclui o processamento ponta a ponta** nem habilita o endpoint na aplicação real.

## 2. Mudança de segurança I1

Em `src/mediflow/api/triage_processing.py`, a função `somente_processamento_local` passa a exigir explicitamente `MEDIFLOW_ENV=development`, além dos controles existentes:

- `MEDIFLOW_ENABLE_LOCAL_UPLOADS=true`;
- `MEDIFLOW_ENABLE_LOCAL_TRIAGE=true`;
- origem local segundo `somente_desenvolvimento_local`;
- serviço de triagem homologado **não é configurado automaticamente** (`obter_servico_triagem()` retorna HTTP 503).

Antes deste incremento, a checagem compartilhada de uploads usava `development` como valor padrão se `MEDIFLOW_ENV` não existisse. A proteção específica do processamento agora **falha fechada** nesse caso, mesmo se as duas flags estiverem ativas.

As flags locais **não são autenticação**. A proteção por host de conexão não substitui autenticação/autorização, especialmente atrás de um proxy reverso.

## 3. Cenários de teste

Arquivo: `tests/test_h11_controles_processamento_i1.py`.

1. A aplicação FastAPI principal não monta a rota `/processar`, mesmo com flags habilitadas.
2. `MEDIFLOW_ENV` ausente bloqueia o processamento, ainda que as duas flags estejam ativadas.
3. Ambiente `production`, `staging`, `test`, vazio ou com espaços indevidos: acesso negado.
4. Valores não canônicos da flag de triagem (`1`, `yes`, `on`, `true ` e vazio): acesso negado.
5. Flag de triagem ausente: HTTP 403.
6. Flag de uploads ausente: HTTP 403.
7. Bloqueio ocorre antes da resolução das dependências OCI e do serviço.
8. Adaptadores não configurados: HTTP 503, sem leitura do objeto.
9. Montagem intencional do router com fakes e flags corretas: HTTP 200 apenas demonstrativo, `armazenamento_oci.status=pendente`.

Todos os testes usam FastAPI `TestClient` e `FakeOCI`. O retorno 200 de demonstração **não comprova extração, roteamento ou persistência reais**.

## 4. Execução

Na raiz do repositório, em branch separada criada a partir da `develop`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_h11_controles_processamento_i1.py -rx
.\.venv\Scripts\python.exe -m pytest -q tests/test_api_triage_processing.py tests/test_h11_controles_processamento_i1.py -rx
.\.venv\Scripts\python.exe -m pytest -q -k "not fluxo_api_com_gemini_real"
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
git diff --check
```

Registrar totais reais da execução e estado da CI no PR; não antecipar a aprovação.

### Evidência da execução local — 09/11/2026

- Branch: `fix/h11-ambiente-explicito-triagem`.
- Testes específicos H11: 17 aprovados.
- Testes combinados da API e H11: 43 aprovados.
- Suíte geral: 297 aprovados, 1 excluído e 1 xfailed conhecido do I4.
- `compileall`: sem erros.
- `git diff --check`: sem erros.
- CI Python 3.12/3.13: pendente.
- Serviços externos: não utilizados.
- Endpoint `/processar`: permanece não registrado na aplicação principal.

## 5. Critério de aceite e limites

- Rota ausente do `app.py` normal, inclusive do OpenAPI/Swagger da aplicação principal.
- Bloqueio por padrão e por ambiente não explicitamente autorizado.
- Nenhum acesso a OCI, serviço ou extração antes da checagem de permissão.
- Não há segredos, documentos clínicos reais ou chamadas externas nos testes.
- Nenhuma alteração em contratos canônicos, regras I4, I2, I3 ou infraestrutura I5.
- Suíte geral e CI Python 3.12/3.13 sem regressões.

**H11 permanece parcial:** a composição segura dos componentes reais, autenticação/autorização, limites de processamento, idempotência e registro controlado do router ainda são tarefas futuras. Não expor `/processar` em produção nem habilitá-lo automaticamente no `app.py`.

Referências: [documentação da rota](12_api_processamento_triagem.md), [critérios do MVP](16_criterios_homologacao_mvp.md) e [guia de colaboração](../CONTRIBUTING.md).
