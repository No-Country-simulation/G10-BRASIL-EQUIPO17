# MediFlow — API HTTP demonstrativa local (fixtures e FakeOCI)

## Objetivo

Disponibilizar a rota `POST /v1/triagens/arquivos/{documento_id}/{arquivo_id}/processar`
para integração preliminar com Streamlit. A rota já existia, mas **não** era registrada na API
principal. Este incremento usa uma **aplicação separada** (`mediflow.api.app_demo_local:app`),
sem alterar `mediflow.api.app` ou o endpoint protegido por H11.

**Componentes:** FastAPI e orquestração verdadeiros, base RAG local verdadeira, motor
determinístico e LangGraph verdadeiros, confirmação independente do documento original,
**extração de gabaritos sintéticos (não Gemini)** e **FakeOCI em memória (não Oracle Cloud)**.

Somente aceita processamento com resultado válido dos originais sintéticos oficiais
`DOC-001`, `DOC-002` e `DOC-005`: um upload arbitrário não pode receber classificação
ou evidências de outro documento. Upload/manifesto pode ser registrado antes da rejeição.

## Segurança e limites

- **Desenvolvimento local exclusivo:** executar somente em `127.0.0.1`, um processo e
  sem proxy de exposição; nenhuma autenticação ou autorização para público foi implementada.
- As variáveis `MEDIFLOW_ENV=development`, `MEDIFLOW_ENABLE_LOCAL_UPLOADS=true`,
  `MEDIFLOW_ENABLE_LOCAL_TRIAGE=true` e `MEDIFLOW_ENABLE_LOCAL_DEMO=true` são obrigatórias.
- `GET /demo/estado` e o cabeçalho `X-MediFlow-Mode` identificam a simulação.
- `armazenamento_oci.status=confirmado` no JSON significa **apenas confirmação FakeOCI**.
- Todos os objetos se perdem quando a aplicação reinicia. Não usar `--reload` nem `--workers`.
- Não usar documentos reais de pacientes, não enviar arquivos para terceiros, não usar
  para decisões clínicas e não disponibilizar em rede, internet ou servidores públicos.
- Não adicionar essa aplicação ao `app.py` principal nem introduzir uma configuração
  que selecione automaticamente este modo em produção.
- Reprocessar um mesmo arquivo gera novas execuções (sem idempotência); o Streamlit
  deve mostrar isso e evitar cliques duplicados na interface.

## Executar em PowerShell (Windows)

Na raiz do repositório e com venv previamente criado:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,ai]"
$env:MEDIFLOW_ENV = "development"
$env:MEDIFLOW_ENABLE_LOCAL_UPLOADS = "true"
$env:MEDIFLOW_ENABLE_LOCAL_TRIAGE = "true"
$env:MEDIFLOW_ENABLE_LOCAL_DEMO = "true"
.\.venv\Scripts\python.exe -m uvicorn mediflow.api.app_demo_local:app --host 127.0.0.1 --port 8000
```

Abrir Swagger: `http://127.0.0.1:8000/docs`. Ver o aviso do modo:
`http://127.0.0.1:8000/demo/estado`.

Em outra janela PowerShell, enviar uma amostra oficial:

```powershell
curl.exe -sS -X POST "http://127.0.0.1:8000/v1/triagens/arquivos" `
  -F "documento_id=DOC-001" `
  -F "canal_origem=demo_local" `
  -F "arquivo=@amostras/pdf/DOC-001_laudo_laboratorial_rotina.pdf;type=application/pdf"
```

Da resposta JSON, copiar o `arquivo_id` e usar:

```powershell
$arquivoId = "COLE_AQUI_O_ARQUIVO_ID"
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/v1/triagens/arquivos/DOC-001/$arquivoId/processar" |
  ConvertTo-Json -Depth 16
```

O resultado será `R005` para DOC-001, `R001` para DOC-002 e `R002` para DOC-005.
**Não é execução Gemini ou persistência Oracle.**

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_http_demo_local.py -rx
.\.venv\Scripts\python.exe -m pytest -q -k "not fluxo_api_com_gemini_real"
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
```

## Interface Streamlit

O frontend pode enviar upload via `POST /v1/triagens/arquivos` (multipart com
`documento_id`, `canal_origem`, `arquivo`) e depois chamar `POST .../processar`,
utilizando os campos do contrato `ResultadoTriagem` (documento, classificação,
regras, evidências, RAG, armazenamento). **Exibir uma indicação permanente**:
`DEMONSTRAÇÃO LOCAL — Gemini simulado por fixtures; OCI simulada em memória`.
Nunca apresentar porcentagem de confiança calibrada, precisão real ou dados clínicos.

## Próxima etapa

Após homologação Gemini, criar integração separada com extrator real e OCI real
controlada, mantendo isolamento, teste H11/H12, proteção de credenciais e os critérios
H01–H14. Não trocar dependências silenciosamente nem promover o modo demo para produção.
