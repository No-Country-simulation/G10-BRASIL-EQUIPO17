# MediFlow — Interface Streamlit

Interface de triagem e roteamento documental para o protótipo educacional MediFlow. A interface consome os resultados retornados pela API FastAPI: não gera extrações ou decisões próprias. No modo demonstrativo, a API utiliza resultados de extração de referência (fixtures) e armazenamento temporário em memória (FakeOCI), sem depender de credenciais ou serviços externos.

## Executar localmente (Windows / PowerShell)

A partir da raiz do repositório, com o ambiente virtual Python criado conforme o [README principal](../../../README.md), instale as dependências:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[dev,ai,ui]'
```

**Terminal 1 — API demonstrativa:**

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path "src"
$env:MEDIFLOW_ENV = "development"
$env:MEDIFLOW_ENABLE_LOCAL_UPLOADS = "true"
$env:MEDIFLOW_ENABLE_LOCAL_TRIAGE = "true"
$env:MEDIFLOW_ENABLE_LOCAL_DEMO = "true"
$env:MEDIFLOW_ENABLE_LOCAL_GEMINI = "false"
$env:MEDIFLOW_ENABLE_LOCAL_OCI = "false"
.\.venv\Scripts\python.exe -m uvicorn mediflow.api.app_demo_local:app --host 127.0.0.1 --port 8000
```

**Terminal 2 — Interface** (também na raiz do repositório):

```powershell
$env:PYTHONPATH = Join-Path (Get-Location).Path "src"
$env:MEDIFLOW_API_URL = "http://127.0.0.1:8000"
.\.venv\Scripts\python.exe -m streamlit run src/mediflow/ui/app.py --server.address 127.0.0.1 --server.port 8501
```

Abra `http://127.0.0.1:8501`. A barra lateral indica a conexão com a API e o modo de execução. Os resultados do modo demonstrativo são temporários: reiniciar a API elimina os registros em memória.

As configurações para validação controlada com Gemini real ou OCI Object Storage, assim como as instruções de execução em Linux, estão no [README principal](../../../README.md). O uso de serviços reais exige configuração e autorização específicas; não é necessário para reproduzir a demonstração.

| Variável | Padrão | Descrição |
|---|---|---|
| `MEDIFLOW_API_URL` | `http://127.0.0.1:8000` | URL base da API FastAPI |
| `MEDIFLOW_API_TIMEOUT` | `120` | Timeout (s) das requisições |

## Funcionalidades e cenários de demonstração

| Página | Funcionalidade |
|---|---|
| Visão geral | Indicadores, gráficos, filtros e consulta dos documentos. Finalizados reúne processados, aprovados, corrigidos e rejeitados, sem equiparar rejeição a aprovação. |
| Enviar documento | Envio de arquivo ou texto sintético, pré-visualização, processamento e resumo do resultado. A remoção da entrada limpa seu resumo da tela, sem excluir o histórico da API. |
| Resultado da análise | Regra principal, prioridade e destino originais, indicador de qualidade documental, evidências e rastreabilidade. A decisão humana e as alterações registradas aparecem separadamente. |
| Fila de auditoria | Consulta de documentos que exigem avaliação humana, aprovação, correção ou rejeição. A saída da fila depende da confirmação do registro da revisão. |

Utilize os arquivos originais em [`amostras/`](../../../amostras/) ou os atalhos de texto disponíveis na interface:

| Cenário | Arquivo | Regra | Encaminhamento original |
|---|---|---|---|
| DOC-001 | `DOC-001_laudo_laboratorial_rotina.pdf` | R005 | Prontuário documental |
| DOC-002 | `DOC-002_laudo_imagem_alerta.pdf` | R001 | Fila prioritária de avaliação humana |
| DOC-005 | `DOC-005_receita_ilegivel.png` | R002 | Auditoria humana |

As composições locais de processamento restringem a triagem aos documentos sintéticos oficiais. Mantenha o nome e o conteúdo original dos arquivos. No modo demonstrativo, arquivos externos às amostras são recusados pela API antes da persistência, com HTTP 422 (`AMOSTRA_NAO_AUTORIZADA`). O modo texto também verifica se o conteúdo corresponde a uma amostra autorizada. Para extração real de imagens, instale o Tesseract OCR conforme as instruções do README principal.

## Estrutura

```text
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

Os caminhos estão em `config.py` (`ENDPOINTS`); a tradução do JSON para as páginas fica em `models.py` (`normalize_document`). A fonte canônica do contrato é [`src/mediflow_contracts/models.py`](../../mediflow_contracts/models.py).

| Método | Caminho | Uso na interface | Disponibilidade |
|---|---|---|---|
| GET | `/h16/estado`, `/gemini/estado`, `/demo/estado`, `/health` | Indicador de conexão e modo | Conforme a aplicação API |
| POST | `/v1/triagens/arquivos` | Envio multipart: `documento_id`, `canal_origem`, `arquivo` → `ReciboArquivo` | Implementado |
| POST | `/v1/triagens/arquivos/{documento_id}/{arquivo_id}/processar` | Processamento → `ResultadoTriagem` | Aplicações locais |
| POST | `/v1/triagens/texto` | Entrada textual (`EntradaTexto` → `ResultadoTriagem`), com atalhos para `amostras/texto/` | Aplicações locais; API principal responde 501 |
| GET | `/v1/triagens/{documento_id}` | Consulta do resultado | Aplicações locais |
| GET | `/v1/triagens?status=` | Visão geral e fila de auditoria | Aplicações locais |
| POST | `/v1/triagens/{documento_id}/revisao` | Decisão humana (`aprovar`, `corrigir`, `rejeitar`) | Aplicações locais |

Para arquivos, o `documento_id` vem do prefixo do nome (`DOC-001_laudo....pdf` → `DOC-001`). Sem prefixo válido, a interface gera `UI-AAAAMMDDhhmmss-XXXXXX`. O canal enviado é `interface_streamlit`.

Antes do envio, a interface verifica extensão, assinatura binária e tamanho (até 10 MiB), além do limite de 10 páginas para PDFs quando a biblioteca de leitura está disponível. A API aplica suas próprias validações de entrada.

## Revisão humana e rastreabilidade

As rotas de consulta e revisão estão em [`triage_review.py`](../api/triage_review.py) e são disponibilizadas pelas aplicações locais `app_demo_local`, `app_gemini_local` e `app_h16_local`, não pela API principal.

O `ResultadoTriagem` v0.1 é retornado com os campos aditivos `recebido_em` e `revisao_humana` (nulo enquanto não há decisão associada à execução). A revisão é registrada separadamente em `revisoes/{documento_id}/…json`, vinculada à execução exata do resultado. O resultado original permanece inalterado. Correções e alterações informadas durante rejeições são exibidas sem modificar os dados originalmente extraídos ou transformar uma rejeição em aprovação.

Na demonstração e na validação da extração com Gemini real, os registros ficam na FakeOCI em memória. A persistência e recuperação da revisão humana na OCI Object Storage foram comprovadas em uma validação controlada com fixtures sintéticas, sem chamadas Gemini reais. O reprocessamento não herda automaticamente revisões anteriores. Consulte o [relatório de persistência e revisão humana](../../../docs/31_h17_homologacao_persistencia_oci_real.md).

### Integridade das correções humanas — PR #74

As correções parciais informadas pelo revisor são verificadas contra os modelos Pydantic do contrato documental. Campos desconhecidos, tipos incompatíveis e campos não editáveis são rejeitados antes da persistência, com HTTP 422 e código `CORRECOES_INVALIDAS`. Uma revisão inválida não deve gerar novo registro nem substituir o resultado original.

As operações de registro de revisão são sincronizadas localmente com `RLock`. Essa sincronização protege apenas threads do mesmo processo, sem oferecer garantia de concorrência entre múltiplos processos, workers ou instâncias. O revisor permanece sem autenticação, conforme as limitações existentes.

Ver [PR #74](https://github.com/No-Country-simulation/G10-BRASIL-EQUIPO17/pull/74) e os testes de regressão da API.

### Consulta por sessão e isolamento entre APIs

Quando a API não disponibiliza as rotas de consulta e revisão, a interface utiliza somente os resultados que a própria API retornou naquela sessão do navegador e exibe o aviso **Dados desta sessão do navegador** na Visão geral e na Fila de auditoria.

Quando `recebido_em` não está disponível, o horário em que a interface recebeu o resultado (`ui_registrado_em_utc`) é utilizado nos filtros temporais e identificado com `*`. Nesse modo, a revisão humana é identificada como indisponível e seus controles ficam desabilitados.

Os registros temporários da sessão e o último resultado usado nas telas estão vinculados à URL do backend. A troca de servidor não mistura resultados de APIs diferentes. Registros antigos sem origem identificada não são reutilizados. Esse armazenamento por sessão não constitui histórico permanente nem autenticação.

## Testes e escopo de utilização

Os testes automatizados da interface ficam em [`tests/test_ui_interface.py`](../../../tests/test_ui_interface.py). A regressão consolidada do projeto registrou 601 testes offline aprovados e três testes com Gemini real deselecionados.

O MediFlow utiliza apenas documentos fictícios neste escopo demonstrativo. O nome do revisor é declarativo, sem autenticação de identidade. As decisões são documentais e administrativas: a aplicação não diagnostica, não prescreve, não autoriza procedimentos nem substitui profissionais de saúde. O indicador de qualidade é heurístico, não uma probabilidade de acerto clínico.
