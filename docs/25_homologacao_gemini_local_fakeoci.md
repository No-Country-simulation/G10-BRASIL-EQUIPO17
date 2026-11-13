# MediFlow — Composição HTTP de homologação Gemini + FakeOCI (local)

## Objetivo

Preparar a composição **opcional** `ExtratorGemini` → validação de integridade
→ confirmador independente do original → RAG local → regras determinísticas e
LangGraph → persistência **FakeOCI em memória**. A API principal e a demonstração
por fixture permanecem intactas. O contrato público continua sendo
`ResultadoTriagem v0.1`.

## Status de evidência

- Testes desta entrega: extrator **injetado e controlado**, **nenhuma chamada real**
  ao Gemini ou OCI. Não demonstram acurácia, custo ou latência reais do Gemini.
- O cliente real é instanciado somente quando o servidor é configurado com
  autorização explícita e chave `GEMINI_API_KEY`.
- O processamento real do Gemini depende da homologação da extração da Júlia;
  divergências nos resultados devem ser documentadas, **nunca** resolvidas
  alterando gabaritos apenas para passar nos testes.
- Não confundir com a homologação H09 (OCI real com fixture); aqui o armazenamento
  continua **exclusivamente em memória**.

## Homologação real do extrator Gemini — 12/11/2026

### Escopo executado

Foi realizada homologação real do adaptador de extração documental com chamadas à API do Gemini, utilizando exclusivamente as amostras sintéticas oficiais do projeto.

Modelo configurado durante a execução: `gemini-3.1-flash-lite`.

| Documento | Amostra | Resultado | Tempo observado |
|---|---|---|---:|
| DOC-001 | Laudo laboratorial de rotina (PDF) | Aprovado | 4,10 s |
| DOC-002 | Laudo de imagem com alerta (PDF) | Aprovado | 6,14 s |
| DOC-005 | Receita ilegível (PNG) | Aprovado | 19,44 s |

Os três testes reais foram executados individualmente e passaram.

### Correção identificada durante a homologação

No DOC-002, foi identificada uma divergência na associação das evidências do marcador explícito de urgência.

O Gemini preenchia o sinal documental, mas não associava uma evidência independente ao campo `sinais_documentais.marcador_urgencia_explicito`.

O prompt do extrator foi ajustado para exigir evidências independentes para:

- `sinais_documentais.marcador_urgencia_explicito`;
- `sinais_documentais.transcricao_marcador_urgencia`, quando preenchido.

Os dois campos podem utilizar o mesmo trecho literal do documento, mas precisam possuir evidências próprias.

Após a correção, o teste real do DOC-002 passou.

### Testes automatizados

Execução da suíte sem chamadas reais ao Gemini:

```bash
pytest -q -k "not fluxo_api_com_gemini_real"
```

Resultado em 12/11/2026:

```text
463 passed, 3 deselected in 7.39s
```

Os três testes desconsiderados nessa execução correspondem aos casos reais parametrizados do Gemini, que foram executados separadamente.

### Limites da evidência

- Os resultados demonstram que os três casos sintéticos passaram nas execuções observadas.
- Os tempos são observações individuais, não uma avaliação estatística de latência.
- Não representam avaliação de acurácia geral, custo operacional ou estabilidade sob carga.
- Esta homologação não comprova persistência em OCI real.
- Não representa homologação integral da composição HTTP com LangGraph.
- O projeto permanece um protótipo educacional, sem finalidade de diagnóstico ou decisão clínica.

### Registro da correção

Commit: `1029233` — `fix(i2): reforçar evidências de urgência no Gemini`.

Branch: `feat/i2-homologacao-gemini`.

## Restrições essenciais

- Somente os bytes e nomes **exatamente iguais** às amostras oficiais `DOC-001`,
  `DOC-002` e `DOC-005` podem ser encaminhados ao extrator Gemini.
- Aplicação **local sem autenticação**, executar somente em `127.0.0.1`, um processo,
  sem `--reload`, sem proxy ou túnel. Não disponibilizar na rede/internet.
- Usar somente arquivos sintéticos, nunca dados reais de pacientes.
- Todo o armazenamento é volátil; se a aplicação reiniciar, arquivos e resultados
  desaparecerão. Não utilizar no Streamlit público.
- Reprocessamentos criam execuções novas; evitar cliques duplicados.
- O JSON pode informar `armazenamento_oci.status="confirmado"`: isto se refere
  **apenas à FakeOCI** e nunca prova gravação Oracle real.
- Nenhum teste automatizado desta entrega deve depender de credenciais ou de
  acesso a serviços externos.

## Instalação local

Na raiz do repositório, com Python 3.12 ou 3.13 e ambiente virtual existente:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,ai]"
```

Para **testes automatizados offline** (não configurar chave Gemini):

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_http_gemini_controlado_local.py -rx
.\.venv\Scripts\python.exe -m pytest -q -k "not fluxo_api_com_gemini_real"
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
```

## Iniciar servidor sem permitir chamadas externas

```powershell
$env:MEDIFLOW_ENV = "development"
$env:MEDIFLOW_ENABLE_LOCAL_UPLOADS = "true"
$env:MEDIFLOW_ENABLE_LOCAL_TRIAGE = "true"
$env:MEDIFLOW_ENABLE_LOCAL_GEMINI = "true"
Remove-Item Env:MEDIFLOW_GEMINI_REAL_ACK -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m uvicorn mediflow.api.app_gemini_local:app --host 127.0.0.1 --port 8001
```

- `GET http://127.0.0.1:8001/gemini/estado` indica o modo e se o uso real
  foi autorizado/configurado. Isso não demonstra uma chamada real bem-sucedida.
- `http://127.0.0.1:8001/docs` lista as rotas.
- Upload sintético continua disponível em `POST /v1/triagens/arquivos`.
- O `POST /v1/triagens/arquivos/{documento_id}/{arquivo_id}/processar`
  retorna **503 `GEMINI_REAL_NAO_AUTORIZADO`**, por segurança, até a habilitação.
- Não existe fallback oculto para fixtures nesta aplicação. Os testes injetam
  extrator controlado deliberadamente, mas a execução normal sem autorização falha fechada.

## Execução controlada real — somente após autorização e homologação do extrator

O código suporta chamadas reais **apenas** se, em sessão PowerShell local e
com consentimento para saída de dados sintéticos e consumo de quota, forem
configuradas as seguintes variáveis *além das quatro anteriores*:

```powershell
# Configure GEMINI_API_KEY por um mecanismo privado; nunca coloque a chave no Git.
# Defina a confirmação de uso externo somente quando decidir fazer a homologação:
$env:MEDIFLOW_GEMINI_REAL_ACK = "AUTORIZO_CHAMADAS_GEMINI"
```

Não executar a homologação real automaticamente. Validar antes o PR da Júlia,
quotas/custos, política de dados e comportamento das evidências; registrar
resultado real inclusive se divergir do gabarito. Nunca enviar chave ao chat.

## Para a interface Streamlit

A interface da Maria Eduarda deve **continuar utilizando**
`mediflow.api.app_demo_local:app`, porta 8000, até que esta nova composição
seja homologada e expressamente liberada. Nenhuma mudança de URL é necessária
na integração da interface nesta entrega.

## Arquivos desta entrega

- `src/mediflow/api/app_gemini_local.py`
- `tests/test_http_gemini_controlado_local.py`
- `docs/25_homologacao_gemini_local_fakeoci.md`
