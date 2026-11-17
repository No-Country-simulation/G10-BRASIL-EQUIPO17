# MediFlow — Interface Streamlit

Front-end do sistema de triagem, extração e roteamento de documentos clínicos **sintéticos**.
A interface não tem dados simulados: tudo vem da API, que precisa estar rodando.

## Executar (Windows / PowerShell, na raiz do repositório)

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[dev,ai,ui]'
```

**1. Iniciar uma API** (escolha uma; ver o README raiz):

```powershell
# Demonstração local: extração por fixtures, FakeOCI em memória, sem Gemini
$env:MEDIFLOW_ENV = "development"
$env:MEDIFLOW_ENABLE_LOCAL_UPLOADS = "true"
$env:MEDIFLOW_ENABLE_LOCAL_TRIAGE = "true"
$env:MEDIFLOW_ENABLE_LOCAL_DEMO = "true"
.\.venv\Scripts\python.exe -m uvicorn mediflow.api.app_demo_local:app --host 127.0.0.1 --port 8000

# OU homologação com Gemini real (mesmas três primeiras variáveis, mais):
$env:MEDIFLOW_ENABLE_LOCAL_GEMINI = "true"
$env:MEDIFLOW_GEMINI_REAL_ACK = "AUTORIZO_CHAMADAS_GEMINI"
$env:GEMINI_API_KEY = "<chave do Google AI Studio>"   # nunca commitar
.\.venv\Scripts\python.exe -m uvicorn mediflow.api.app_gemini_local:app --host 127.0.0.1 --port 8000
```

**2. Em outro terminal, iniciar a interface:**

```powershell
.\.venv\Scripts\python.exe -m streamlit run src/mediflow/ui/app.py
```

A barra lateral mostra se a API está conectada e avisa quando o modo é simulado (FakeOCI em memória).
As duas composições locais **só processam as amostras oficiais** de `amostras/`
(`DOC-001`, `DOC-002`, `DOC-005`) com o nome de arquivo original. O DOC-005 é imagem e
exige o Tesseract OCR instalado no sistema.

| Variável               | Padrão                   | Descrição                         |
|------------------------|--------------------------|-----------------------------------|
| `MEDIFLOW_API_URL`     | `http://127.0.0.1:8000`  | URL base da API FastAPI           |
| `MEDIFLOW_API_TIMEOUT` | `120`                    | Timeout (s) das requisições       |

## Estrutura

```
.streamlit/config.toml     # tema visual (na raiz do repositório)
src/mediflow/ui/
  app.py                   # entrada: configuração, barra lateral, navegação
  config.py                # URL, endpoints, rótulos e cores do domínio
  api_client.py            # cliente HTTP + tratamento de erros (APIError)
  models.py                # tradução ResultadoTriagem (v0.1) -> modelo das páginas
  components.py            # badges, cartões, cabeçalhos, mensagens de erro
  navigation.py            # registro de páginas e navegação programática
  views/
    dashboard.py           # 1. Visão geral
    upload.py              # 2. Enviar documento
    result.py              # 3. Resultado da análise
    audit.py               # 4. Fila de auditoria
```

## Rotas usadas

Os caminhos estão em `config.py` (`ENDPOINTS`); a tradução do JSON para as páginas fica
**só** em `models.py` (`normalize_document`). `src/mediflow_contracts/models.py` é a fonte
canônica do contrato.

| Método | Caminho | Uso na UI | Estado na API |
|--------|---------|-----------|---------------|
| GET  | `/gemini/estado`, `/demo/estado`, `/health` | indicador de conexão e modo | implementado (um por app) |
| POST | `/v1/triagens/arquivos` | 1ª etapa do envio: multipart `documento_id`, `canal_origem`, `arquivo` → `ReciboArquivo` | implementado |
| POST | `/v1/triagens/arquivos/{documento_id}/{arquivo_id}/processar` | 2ª etapa: → `ResultadoTriagem` | implementado nas apps locais |
| POST | `/v1/triagens/texto` | aba "Colar texto" | API principal responde 501; ausente nas apps locais |
| GET  | `/v1/triagens/{documento_id}` | página Resultado | implementado nas apps locais |
| GET  | `/v1/triagens?status=` | Visão geral e Fila de auditoria | implementado nas apps locais |
| POST | `/v1/triagens/{documento_id}/revisao` | decisão do auditor (`aprovar`, `corrigir`, `rejeitar`) | implementado nas apps locais |

O `documento_id` vem do prefixo do nome do arquivo (`DOC-001_laudo....pdf` → `DOC-001`);
sem prefixo válido, a UI gera `UI-AAAAMMDDhhmmss-XXXXXX`. Envia `canal_origem = "interface_streamlit"`.
Antes do envio, valida extensão, assinatura binária, tamanho (até 10 MB) e páginas do PDF (até 10).

As três rotas de consulta e revisão ficam em `src/mediflow/api/triage_review.py` e só existem nas
apps locais (`app_demo_local`, `app_gemini_local`). Elas devolvem o `ResultadoTriagem` v0.1 com dois
campos aditivos: `recebido_em` e `revisao_humana` (null até a primeira decisão). Cada decisão é
gravada como objeto imutável em `revisoes/{documento_id}/…json`; o resultado original nunca é
alterado e as correções do auditor ficam só no registro da revisão. Como o armazenamento é a
FakeOCI em memória, tudo some quando a API é reiniciada.

Contra a API principal, que não tem essas rotas, a UI volta a usar os `ResultadoTriagem` que
**a própria API devolveu nesta sessão** do navegador, e a decisão do auditor mostra um erro
explicando que a API não registra revisões.
