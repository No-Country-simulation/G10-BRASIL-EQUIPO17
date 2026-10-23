# Relatório de validação local — Dia 2

## Escopo validado
- Três JSON Schemas são válidos (Draft 2020-12) e iguais aos gerados por Pydantic.
- Fixtures DOC-001/DOC-002/DOC-005 validam por JSON Schema e Pydantic.
- Os três roteamentos coincidem com o gabarito aprovado no Dia 1.
- Precedência R001 na urgência com ambiguidade preserva R002 no histórico.
- LLM sozinha não pode habilitar R001 sem confirmação externa do texto original.
- Falha de RAG não rebaixa alerta previamente verificado.
- Dosagem ilegível não aceita valor inventado no campo confirmado.
- OCI não pode declarar `confirmado` sem bucket e chaves obrigatórias no contrato.
- Destinos correspondem ao catálogo de categorias aprovado no Dia 1.
- Amostras sintéticas originais estão incluídas e são acessíveis.

**Resultado local:** 25 testes passaram (`PYTHONPATH=src python -m pytest -q`).

## O que não foi validado ainda
- Acurácia de IA e extração de dados **reais**; fixtures contêm dados sintéticos transcritos.
- Compilação e execução do grafo LangGraph (diagrama somente).
- API HTTP FastAPI (rotas planejadas, não implementadas).
- Consulta RAG/índice vetorial real.
- Gravação/leitura OCI; exemplos mantêm `status=pendente`.
- Avaliação por profissionais habilitados, métricas clínicas ou conformidade de produção.

## Como reproduzir
```bash
python -m pip install -r requirements-dev.txt
python scripts/exportar_schemas.py
python scripts/gerar_exemplos.py
PYTHONPATH=src python -m pytest -q
```
