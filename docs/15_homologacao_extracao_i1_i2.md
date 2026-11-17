# MediFlow — Homologação I1/I2 (incremento controlado)

**Escopo:** FastAPI/orquestração I1 + `ExtratorGemini` I2, com documentos exclusivamente sintéticos. O arquivo de testes não acessa Gemini, OCI ou LangGraph pela rede; o cliente Gemini é simulado. A leitura de PDF com PyMuPDF e o OCR de PNG com Tesseract são **reais**. I4 usa apenas gerador demonstrativo de contrato, nunca decisão clínica.

## Objetivo

Validar que `ServicoTriagem` aceita a implementação real de `ExtratorGemini` como `ExtratorDocumento`, preservando IDs, tipo de entrada, SHA-256, trechos de evidência e tratamento seguro de exceções. Preparar as futuras integrações I1/I3/I4/I5 sem alterar os módulos das outras pessoas.

## Arquivos

- `tests/test_homologacao_extracao_i1_i2.py`: oito testes controlados e independentes, sem credenciais reais.
- `docs/15_homologacao_extracao_i1_i2.md`: esta documentação.

## Cenários automatizados

1. PDF sintético digital: PyMuPDF real, resultado Gemini simulado, fluxo I1 e roteamento demonstrativo de rotina (R005).
2. PNG sintético: OCR Tesseract real, resultado Gemini simulado, roteamento demonstrativo para auditoria por dosagem ilegível (R002).
3. Sinal de urgência alegado pela LLM não substitui confirmação independente do original.
4. Evidência textual inexistente não passa pela validação do extrator.
5. `documento_id` divergente é rejeitado antes da decisão.
6. Indisponibilidade simulada do Gemini gera código público sanitizado.
7. SHA-256 divergente impede invocar o extrator.
8. Erro simulado de OCR não vaza detalhes e não invoca o Gemini.

Os roteamentos R002/R005 exercitados **não** validam o motor final I4. O gerador legado `gerar_exemplo_de_contrato` existe exclusivamente para validar contratos durante este incremento.

## Ambiente de teste

No Windows, a partir da raiz do repositório, instalar as dependências opcionais de IA se faltarem: `python -m pip install -e '.[dev,ai]'`. O teste de OCR PNG requer Tesseract OCR com o idioma `por` configurado no PATH. Conferir em PowerShell: `tesseract --list-langs`.

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_homologacao_extracao_i1_i2.py
.\.venv\Scripts\python.exe -m pytest -q -k "not fluxo_api_com_gemini_real"
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
git diff --check
```

### Critérios de aceite

- Oito novos testes aprovados, mais a suíte preexistente sem regressões.
- Nenhuma chamada externa, chave, token ou dado de paciente real nos testes.
- Nenhuma mudança em `app.py`, extração I2, módulos I3/I4/I5 ou contratos canônicos.
- `armazenamento_oci.status='pendente'` porque não há persistidor neste incremento.
- Nenhuma afirmação de homologação real da LLM, persistência real OCI ou fluxo clínico.

## Etapa separada: homologação real da API Gemini

O repositório já contém `test_fluxo_api_com_gemini_real`, ignorado quando `GEMINI_API_KEY` está ausente. Essa execução requer chave válida, controle de custos e documento estritamente sintético; depende de coordenação com I2. Nunca incluir chave em comando publicado, log, Git ou mensagem. A autorização, o modelo disponível e os resultados devem ser conferidos antes de declarar extração externa homologada.

## Limitações e próximos passos

- Este incremento não habilita endpoint `/processar` nem altera autenticação.
- I3 RAG e I4 motor final permanecem pendentes de integração; os testes não exercitam esses módulos reais.
- Após revisão do PR, executar homologação real e registrada de I2, depois composição I1/I2/I3/I4/I5 e testes ponta a ponta em ambiente de desenvolvimento protegido.
