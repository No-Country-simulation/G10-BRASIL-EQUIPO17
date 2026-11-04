# MediFlow — Adaptador I1 ↔ I3 para referências RAG

**Estado:** incremento preparatório independente. Escopo de hackathon educacional **apenas com documentos sintéticos**. A API pública e o pipeline com Gemini/OCI/LangGraph continuam desabilitados nesta etapa.

## Objetivo

Fazer a ponte entre duas interfaces existentes sem alterar seus responsáveis:

- **I1**, `ServicoTriagem` / `ProvedorRAG`: `buscar(extracao: ExtracaoIA) -> RecuperacaoRAG`;
- **I3**, PR #16 (ainda Draft): `RecuperadorReferencias.buscar(ConsultaRAG(texto, limite)) -> RecuperacaoRAG`.

`AdaptadorRAGI3` recebe um recuperador e um **construtor de ConsultaRAG injetados**. Isso permite compilar e testar o PR do I1 isoladamente contra a `develop`, sem importar o código ainda não integrado da Ana.

## Fluxo

```text
ServicoTriagem (I1)
    -> AdaptadorRAGI3.buscar(ExtracaoIA)
       -> construir_texto_consulta(ExtracaoIA)
          -> texto controlado: categoria de documento e estados de campos
       -> fabrica_consulta(texto=..., limite=3)
       -> recuperador.buscar(ConsultaRAG)  [I3, quando integrado]
       -> valida e devolve RecuperacaoRAG v0.1
    -> ServicoTriagem encaminha referências ao decisor I4
```

**Privacidade e minimização:** a consulta NÃO incorpora `documento_id`, nome/identificador do paciente, CRM, nome/dose textual de medicamento, valores de exames, CID, especialidade livre, resumo, evidências nem transcrição de urgência. Apenas vocabulário previamente definido para as 7 categorias e estados (`ausente`, `ilegivel`, `conflitante`) de nome/dosagem. Não incluir dados livres sem revisão de privacidade.

**Responsabilidades:** O RAG recupera referências e não confirma alerta de urgência, não aplica R001–R006 nem determina fila. A confirmação independente no original e a decisão pertencem ao I4. Uma busca textual não valida o conteúdo do documento nem garante relevância. O I1 já transforma exceções do recuperador em `RecuperacaoRAG(status="falha", erro_codigo="RAG_ERRO_INTEGRACAO")`, sem interromper o motor de decisão.

## Como conectar após o merge do PR #16

O trecho abaixo é **apenas um exemplo futuro**. Não executá-lo na `develop` antes de o I3 ser integrado e homologado.

```python
from mediflow.api.triage_rag_adapter import AdaptadorRAGI3
from mediflow.rag.carregador import criar_recuperador_padrao
from mediflow.rag.port import ConsultaRAG

recuperador_i3 = criar_recuperador_padrao()
adaptador_rag = AdaptadorRAGI3(
    recuperador=recuperador_i3,
    fabrica_consulta=ConsultaRAG,
    limite=3,
)
# Injetar adaptador_rag como `recuperador` em ServicoTriagem,
# ou na futura composição I1/I5 com montar_servico_triagem_com_oci(...).
```

### Quando o I3 for integrado

1. Conferir que o PR #16 preserva a assinatura de `ConsultaRAG` e `RecuperadorReferencias.buscar`.
2. Executar testes de contrato com o recuperador real local `criar_recuperador_padrao()` e fichas versionadas.
3. Verificar `status`, `fonte_id`, `titulo`, `versao`, `url`, `trecho_relevante`, limite de fontes e relevância qualitativa nas amostras sintéticas.
4. Injetar no I1 apenas depois da homologação. Não modificar regras do I4 nem montar o router HTTP de processamento antecipadamente.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_triage_rag_adapter.py
.\.venv\Scripts\python.exe -m pytest -q -k "not fluxo_api_com_gemini_real"
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
```

Os testes deste PR usam apenas fakes para o I3. Nenhuma chamada de rede, Gemini, OCI ou LangGraph é feita. Não afirmam compatibilidade executada com o PR #16 ainda em Draft; validam a assinatura estrutural divulgada no PR.

## Limitações para a próxima etapa

- A consulta é uma **heurística mínima**, com termos fixos; não possui embeddings, pontuação de confiança nem validação semântica de fontes.
- Fábrica e recuperador são injetados por quem monta o serviço; não são carregados automaticamente.
- O adaptador não substitui controle de acesso, proteção de dados sensíveis, versão de regras, logs seguros ou auditoria.
- Não alterar `app.py`, `triage_service.py`, `triage_processing.py`, os contratos Pydantic ou arquivos sob `src/mediflow/rag/` neste PR.
