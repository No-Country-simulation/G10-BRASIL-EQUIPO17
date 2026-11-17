# MediFlow — H16: composição HTTP local Gemini + OCI (preparação offline)

**Status:** implementação preparatória, **não homologada em OCI/Gemini reais**.
**Base:** `develop` commit `7918199` (H15 integrada). Branch proposta: `feat/h16-http-gemini-oci-real`.

## Objetivo

Montar aplicação FastAPI isolada que reutiliza `receber_documento`, `ServicoTriagem`, Gemini I2, RAG I3, LangGraph/regras I4 e persistência OCI I5, sem publicar a rota de processamento na aplicação principal. Reutiliza contratos Pydantic v0.1 inalterados.

## Controles de segurança

- Aceita **somente** bytes, nome e MIME das amostras oficiais `DOC-001`, `DOC-002` e `DOC-005` **antes** de instanciar o storage de upload e antes de escrever.
- Extrator usa `ExtratorSomenteAmostras` da H15, para uma segunda verificação de integridade antes de invocar o Gemini.
- Exige `127.0.0.1`, `::1` ou `testclient`, `MEDIFLOW_ENV=development`, flags explícitas, bucket `mediflow-docs-dev` e `MEDIFLOW_OCI_REAL_ACK=AUTORIZO_OCI_DEV_H16`.
- Para uma chamada Gemini real, a dependência I2 da H15 também exige `MEDIFLOW_GEMINI_REAL_ACK=AUTORIZO_CHAMADAS_GEMINI` e `GEMINI_API_KEY` configurada.
- O endpoint `GET /h16/estado` não acessa serviços externos e **não comprova** execução real.
- Não iniciar em `0.0.0.0`, não usar `--reload` ou múltiplos workers; não processar dados de pacientes reais. A flag de localidade **não é autenticação**.
- Cada upload novo cria original e manifesto; cada processamento novo cria histórico e resultado. A API ainda não implementa idempotência: repetir POST pode gerar custos e objetos adicionais. Não repetir chamadas reais automaticamente.
- Tratamento de falhas e integridade reutiliza I1/I5. Não há transação atômica de objetos nem limpeza destrutiva.

## Fila e revisão humana no bucket dev

A H16 também registra as rotas de `triage_review.py`, sobre o **mesmo bucket** `mediflow-docs-dev`:

- `GET /v1/triagens?status=` e `GET /v1/triagens/{documento_id}` listam/consultam os resultados persistidos, com `recebido_em` e `revisao_humana`.
- `POST /v1/triagens/{documento_id}/revisao` grava a decisão (`aprovar`, `corrigir`, `rejeitar`) como objeto **imutável** em `revisoes/{documento_id}/…json`. O `ResultadoTriagem` original nunca é alterado; correções ficam só no registro da revisão.
- Mesmas travas da H16 (localhost, flags, consentimentos e bucket dev). **Sem autenticação:** o nome do revisor é declarativo; cada decisão é uma gravação real no bucket.
- A interface Streamlit reconhece o modo pela rota `/h16/estado` ("H16 (Gemini + OCI real)") e habilita a fila de auditoria com revisão.

Na homologação real, depois do processamento, registrar uma revisão do DOC-005 e conferir o objeto em `revisoes/` e a leitura via `GET /v1/triagens/DOC-005`.

## Arquivos novos

- `src/mediflow/api/app_h16_local.py` — composição isolada H16.
- `tests/test_http_h16_controlado_local.py` — testes com Gemini por fixture e OCI em memória, **sem acessos externos**.
- `docs/28_h16_preparacao_http_gemini_oci.md` — esta documentação.

## Execução offline (sem serviços externos)

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_http_h16_controlado_local.py -rx
.\.venv\Scripts\python.exe -m pytest -q -k "not fluxo_api_com_gemini_real"
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
git diff --check
git status -sb
```

Os testes injetam explicitamente `ObjectStorageMemoria` e `ExtratorFixtureSintetica`; nunca constroem um cliente OCI nem chamam o Gemini. As flags e o consentimento **nos testes** não autorizam operações reais.

## Próximos portões — não executados nesta entrega

1. CI Python 3.12 e 3.13 sem regressão, revisão por I5/I2, testes negativos e revisão de segredos.
2. Verificar perfil IAM, região, namespace e bucket OCI DEV, custo e política de retenção, sem expor credenciais.
3. Executar **uma única** homologação autorizada com `DOC-001`, capturando códigos HTTP, hashes, chaves de objetos sanitizadas, regra R005 e leitura de retorno OCI.
4. Ampliar para DOC-002 e DOC-005 somente após aprovação do primeiro cenário, controle de custos e testes de falhas.

**Esta entrega é preparação, não prova de H16 real.**
