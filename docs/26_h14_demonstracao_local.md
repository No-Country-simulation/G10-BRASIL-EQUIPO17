# MediFlow — H14: evidência técnica da demonstração local

## Objetivo

Gerar evidência auditável para os três cenários sintéticos oficiais com o
**mesmo aplicativo HTTP demonstrativo** que será consumido pelo Streamlit,
sem exigir a disponibilidade da interface, da chave Gemini ou da OCI real.

O script executa o ciclo `upload → recibo → /processar → ResultadoTriagem`
via FastAPI `TestClient` no processo local. Não inicia servidor, não cria
conexões Gemini/OCI e não publica endpoints.

## Componentes verdadeiros e simulados

- **Reais locais:** validação do upload e SHA-256, FastAPI/orquestração,
  recuperador RAG local, confirmador independente de alerta, motor
  determinístico e LangGraph.
- **Simulados:** extração a partir dos JSONs de referência e FakeOCI em memória.
- **Não executados:** Gemini real, OCI real, Streamlit e deploy público.

**Aprovação H14 deste script:** `aprovado_com_simulacao` para demonstração técnica
local; **não equivale à homologação ponta a ponta do MVP completo**.

## Critérios verificáveis

| Cenário | Regra | Destino | Revisão | Status |
|---|---|---|---|---|
| DOC-001 | R005 | `prontuario_documental` | Não | `processado` |
| DOC-002 | R001 | `fila_prioritaria_avaliacao_humana` | Sim | `aguardando_auditoria` |
| DOC-005 | R002 | `auditoria_humana` | Sim | `aguardando_auditoria` |

O teste verifica resposta HTTP 201 no upload, HTTP 200 no processamento,
identidade e SHA-256 do arquivo, categoria, regra, destino, revisão, estado,
RAG consultado, armazenamento confirmado **somente em FakeOCI**, leitura de
retorno da simulação e ausência de inferência de dose para DOC-005.

## Execução no PowerShell

Na raiz do repositório, em uma branch exclusiva criada a partir de `develop`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_h14_demonstracao_local.py -rx
.\.venv\Scripts\python.exe scripts/homologar_h14_demo_local.py
.\.venv\Scripts\python.exe -m pytest -q -k "not fluxo_api_com_gemini_real"
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
git diff --check
```

O script imprime um resumo por cenário e grava o JSON
`docs/evidencias/h14_demonstracao_local.json` **apenas após os três cenários
serem aprovados**. A execução pode substituir essa evidência, portanto
revisá-la antes de adicioná-la ao PR.

O JSON contém `execucao_id`, timestamps UTC/BRT, `git_commit_base`, modo,
componentes verdadeiros/simulados, códigos HTTP, hash das amostras públicas,
regras e destinos. **Não contém** documentos, nomes de pacientes, resposta
completa de extração, chaves de armazenamento, credenciais ou tokens.

O campo `git_commit_base` indica o HEAD no momento da execução. Se a evidência
for produzida antes do commit que adiciona o próprio script, **o hash reflete
a versão-base testada**, não um commit de entrega já integrado.

### Compartilhamento e revisão

Revisar a evidência JSON e os três arquivos de código/documentação com
`git diff --check` antes de fazer o commit. Nunca usar `git add .`.

**Este relatório não substitui** a demonstração visual com Streamlit.
Quando a interface estiver pronta, o H14 deve ser complementado com
identificação do commit conjunto, roteiro visual, integração HTTP real local
ou evidência de gravação de tela, e os mesmos três cenários devem ser
reexecutados no ambiente final.

## Critérios de aceite da interface (entrega futura)

- Exibir aviso permanente sobre fixture e FakeOCI.
- Selecionar exclusivamente uma das três amostras oficiais sintéticas.
- Usar upload `multipart/form-data` com `documento_id`, `canal_origem`, `arquivo`.
- Preservar `arquivo_id` recebido e enviá-lo em `/processar`.
- Exibir regra, destino, status, revisão humana, evidências, fontes RAG e
  somente a identificação correta de armazenamento FakeOCI.
- Salvar temporariamente resposta em `st.session_state`, evitar duplo clique e
  tratar 403/404/413/415/422/502/503 sem mostrar segredos ou traceback.
- Não afirmar persistência OCI real, precisão calibrada ou uso clínico.

## Limitações

- O uso do `TestClient` não verifica latência de rede nem a interface Streamlit.
- A FakeOCI é global ao processo, mas o script preserva seu estado preexistente
  e restaura os objetos/flag de falha após a execução.
- Testes posteriores com Gemini real ou OCI real terão registros de homologação
  separados e exigem autorização específica.
