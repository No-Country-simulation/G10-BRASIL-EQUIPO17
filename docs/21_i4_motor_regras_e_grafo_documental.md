# MediFlow — I4 definitivo: motor de regras, confirmação independente e grafo documental

**Responsável técnico:** I1 + I4 (acumulados pelo responsável pela integração). **Escopo:** regras administrativas fictícias para documentos exclusivamente sintéticos. **Não é triagem clínica.**

## 1. Backlog e entregas

| Item | Entrega neste incremento | Critério de validação |
| --- | --- | --- |
| B-008 | Motor determinístico que lê `rules/roteamento.yaml` e `rules/validacao.yaml`, valida invariantes e aplica R001–R006 / V001–V004 | Testes de configuração, campos mínimos e precedência |
| B-009 | Confirmador do marcador textual no **original** PDF/PNG/JPEG sem Gemini ou RAG; R001 prioritária e revisão humana | DOC-002 com marcador expresso; DOC-001 negativo; falhas não viram rotina |
| B-010 | Encaminhamento de campos críticos ausentes/ilegíveis/conflitantes à auditoria | DOC-005 R002, dosagem nula preservada |
| B-011 | R003, R004, R005 e R006 com destino administrativo coerente | DOC-001 R005, casos artificiais dos demais caminhos |
| B-012 | Grafo **condicional de roteamento** executável com LangGraph: validar contratos → motor determinístico → rota R001...R006 → conferir saída | Testes das seis rotas e compatibilidade com `ServicoTriagem` do I1 |

**Limite de B-012:** o grafo deste incremento é o subfluxo de **decisão I4** injetável no I1. A integração completa dos nós externos de I2 (Gemini), I3 (RAG), I5 (OCI) e API em um grafo de ponta a ponta continua pendente; não declarar o MVP concluído por aprovar somente este incremento.

## 2. Arquitetura

```text
DocumentoParaExtracao (original íntegro)
  └─ I1 ServicoTriagem
       ├─ I2 ExtratorDocumento → ExtracaoIA v0.1
       ├─ I4 ConfirmadorAlertaOriginal → bool (sem ler a saída da LLM)
       ├─ I3 ProvedorRAG → RecuperacaoRAG (opcional, não decisório)
       ├─ I4 GrafoDocumentalI4 (ou MotorRegrasDeterministico isolado)
       │    ├─ validar contratos
       │    ├─ avaliar rules/roteamento.yaml + rules/validacao.yaml
       │    ├─ aresta condicional R001 / R002 / R003 / R004 / R005 / R006
       │    └─ conferir regra e rota; retornar ResultadoTriagem v0.1
       └─ I5 PersistidorTriagem (opcional, com confirmação OCI posterior)
```

**Fonte da decisão:** YAMLs canônicos; o grafo **não duplica** condições, destinos ou precedência. R001 só é selecionada quando a leitura independente do original confirmou uma frase explicitamente prevista; o RAG e o Gemini não podem confirmar o próprio alerta. R001 prevalece sobre R002, mas a ambiguidade concomitante permanece registrada. V003 (profissional sem nome) é aviso administrativo, não urgência. `ArmazenamentoOCI.status` continua `pendente` sem persistidor; indicador de qualidade continua `nao_calculado`, com valor `null`.

O reconhecimento de marcador é **literal e conservador**, não um classificador clínico. O confirmador utiliza PyMuPDF e Tesseract do I2 para ler o original, mas não depende da LLM. OCR pode gerar falso negativo ou falso positivo; nenhum documento real deve ser processado. Falha de leitura lança exceção, que o I1 converte em falha sanitizada.

## 3. Arquivos

- `src/mediflow/rules/motor_deterministico.py` — motor, configuração e validação administrativa.
- `src/mediflow/rules/confirmador_alerta.py` — leitura independente do original e marcador expresso.
- `src/mediflow/agents/grafo_documental.py` — LangGraph condicional com seis caminhos.
- `tests/test_motor_deterministico.py` — motor e confirmação sintética.
- `tests/test_grafo_documental_i4.py` — fluxo de decisão LangGraph e integração com I1.
- `tests/test_confirmacao_amostras_i4.py` — verificações sobre os PDFs DOC-001 e DOC-002 reais **do repositório**, mas sintéticos quanto aos dados.
- `docs/21_i4_motor_regras_e_grafo_documental.md` — este documento.

**Não alterados:** contratos Pydantic v0.1, schemas, YAMLs, `app.py`, `triage_service.py`, código I2/I3/I5 e os PRs pendentes.

## 4. Uso local (após instalar dependências)

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,ai]"
.\.venv\Scripts\python.exe -m pytest -q tests/test_motor_deterministico.py tests/test_grafo_documental_i4.py tests/test_confirmacao_amostras_i4.py -rx
.\.venv\Scripts\python.exe -m pytest -q -k "not fluxo_api_com_gemini_real"
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
```

A suíte precisa usar a biblioteca `langgraph` verdadeira, instalada pelo extra `[ai]`; `pytest.importorskip("langgraph")` protege apenas ambientes que não instalaram esse extra, e **skip não é aprovação de B-012**. Verificar que `tests/test_grafo_documental_i4.py` efetivamente executou os testes.

### Composição do I1 (somente protótipo controlado)

```python
from mediflow.api.triage_service import ServicoTriagem
from mediflow.rules.confirmador_alerta import ConfirmadorAlertaOriginal
from mediflow.agents.grafo_documental import GrafoDocumentalI4

servico = ServicoTriagem(
    extrator=extrator_i2,                  # injeção controlada e homologada
    confirmador=ConfirmadorAlertaOriginal(),
    decisor=GrafoDocumentalI4(),
    recuperador=recuperador_i3,            # opcional, quando PR #16 entrar
    persistidor=persistidor_i5,            # opcional, por requisição
)
resultado = servico.executar(documento_verificado, canal_origem="teste_sintetico")
```

Este exemplo **não** deve ser executado com nomes de variáveis fictícios ou exposto em endpoint público. O endpoint `/processar` permanece fora de `app.py` enquanto faltarem autenticação, autorização, limites e política de reprocessamento.

## 5. Evidências e portões

- [x] Três cenários canônicos: DOC-001 R005, DOC-002 R001 e DOC-005 R002.
- [x] R001 > R002, preservando ambas em `regras_disparadas` quando aplicável.
- [x] V001–V004 e alteração insegura do YAML rejeitadas.
- [x] Confirmador em PDFs sintéticos do repositório: DOC-001 negativo, DOC-002 positivo.
- [x] Grafo LangGraph de seis rotas comprovado (sem skip).
- [ ] CI Python 3.12 e 3.13 verde, com revisor de outra frente antes do merge.
- [ ] B-012 ponta a ponta posterior: I2 + I3 + I4 + I5 + API local com três documentos e saída persistida, sem uso clínico.

### Evidência da validação local

- Branch: `feat/i4-motor-regras-langgraph`.
- Testes específicos I4: 44 aprovados.
- Suíte geral: 324 aprovados, 1 excluído e 1 xfailed conhecido.
- LangGraph: versão 1.2.19, executado nos testes.
- `compileall`: concluído sem erros.
- `git diff --check`: sem erros.
- Documentos oficiais sintéticos: DOC-001 e DOC-002 verificados no teste de confirmação.
- Contratos v0.1 e YAMLs canônicos: preservados.
- OCI/Gemini/RAG reais: não utilizados neste incremento.
- CI Python 3.12/3.13: pendente de execução no PR.
- Integração ponta a ponta: pendente.

## 6. Limitações e próximos incrementos

1. **Integração com RAG I3** após PR #16, usando `AdaptadorRAGI3` existente. Não consultar texto livre de paciente na base e não usar o RAG como prova do alerta.
2. **Composição completa da API I1/I4** com adaptadores efetivos e OCI, preservando gates H09–H12 e registro local restrito.
3. **B-012 completo:** modelar/verificar as etapas externas como nós explícitos se a entrega do hackathon exigir a visualização integral em LangGraph; este incremento implementa somente o grafo de decisão condicional, para evitar duplicar a orquestração I1 já testada.
4. **B-015:** homologação real controlada dos três documentos oficiais, evidências sanitizadas, custos e estados.
5. **Segurança operacional:** autenticação/autorização, idempotência, retenção e deploy privado antes de qualquer acesso externo. Sem esses itens, não declarar MVP de uso real.

A responsabilidade pelas entregas I4 nesta implementação é definitiva na organização informada para o desenvolvimento, mas isso não determina o status administrativo de qualquer integrante na plataforma do hackathon.
