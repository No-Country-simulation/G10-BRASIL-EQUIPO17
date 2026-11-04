# MediFlow — Triagem documental com IA (Hackathon ONE G10)

**Equipe:** 6 integrantes · **Plano:** 5 semanas · **Contrato atual:** `v0.1`.

O MediFlow é um protótipo educacional de classificação, extração e roteamento de documentos clínicos **sintéticos**. **Não** oferece diagnóstico, prescrição ou decisão médica. **Não está pronto para uso com dados reais.**

## Situação do código

- **Disponível:** API FastAPI, upload de documentos PDF/PNG/JPEG, validação de arquivos, integração com Oracle Object Storage, extração de texto e OCR com Tesseract, extração estruturada com Gemini, contratos Pydantic e testes automatizados.
- **Integração com IA:** o módulo de extração utiliza a API do Google Gemini, configurada pela variável `GEMINI_API_KEY`.
- **Preview:** existe uma rota de demonstração com respostas simuladas, que não utiliza o Gemini real.
- **Limites de upload:** arquivos de até 10 MB e PDFs com até 10 páginas.
- **Testes:** os testes automatizados podem ser executados localmente. O teste de integração real com Gemini depende de uma chave válida e de disponibilidade do serviço externo.
- **Triagem textual:** a rota `POST /v1/triagens/texto` ainda retorna HTTP 501 para entradas válidas e HTTP 422 para entradas inválidas. O endpoint `GET /health` não comprova disponibilidade do Gemini ou da OCI.

**Importante:** o MediFlow é um protótipo educacional que utiliza documentos exclusivamente sintéticos. Não oferece diagnóstico, prescrição ou decisão médica e não está pronto para uso com dados reais.

## Repositório compartilhado

**GitHub:** https://github.com/No-Country-simulation/G10-BRASIL-EQUIPO17

- `main`: versão estável para demonstrações;
- `develop`: integração de mudanças aprovadas;
- `feat/`, `fix/`, `docs/`, `test/`, `refactor/`, `chore/`: branches temporárias, nomeadas pelo trabalho e **não** pelo dia, data ou nome do integrante.

Veja **[CONTRIBUTING.md](CONTRIBUTING.md)** antes de começar uma alteração.

## Instalação local (Windows / PowerShell)

Pré-requisitos: Git e Python 3.12. Não há dependência de um computador central ligado.
**OCR no Windows:** instale o Tesseract OCR separadamente e certifique-se de que o executável esteja disponível no `PATH` do sistema. O pacote Python `pytesseract` não instala o Tesseract automaticamente.

```powershell
git clone https://github.com/No-Country-simulation/G10-BRASIL-EQUIPO17.git
cd G10-BRASIL-EQUIPO17
git switch develop
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev,ai,cloud]'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn mediflow.api.app:app --reload
```

Acesse `http://127.0.0.1:8000/docs` para testar a API local.

### Configuração das integrações

Para utilizar a extração real com Gemini, configure a variável de ambiente `GEMINI_API_KEY` com uma chave válida da API do Google.

No Linux/macOS:

```bash
export GEMINI_API_KEY="SUA_CHAVE"
```
No Windows PowerShell:

```powershell
$env:GEMINI_API_KEY="SUA_CHAVE"
```

Para utilizar o Oracle Object Storage, configure:

- `OCI_CONFIG_FILE`: caminho do arquivo de configuração OCI.
- `OCI_CONFIG_PROFILE`: perfil utilizado (padrão: `DEFAULT`).
- `OCI_BUCKET`: nome do bucket.
- `OCI_NAMESPACE`: namespace da conta OCI.

**Segurança:** não coloque chaves, tokens ou arquivos de credenciais no repositório. Utilize variáveis de ambiente e mantenha arquivos sensíveis fora do Git.

### Fluxos de extração

O projeto possui dois fluxos distintos:

- **Extração real:** utiliza o Google Gemini para processar o documento e gerar dados estruturados, conforme os contratos do MediFlow. Depende da configuração de `GEMINI_API_KEY` e da disponibilidade do serviço externo.
- **Preview de extração:** a rota `/arquivos/{documento_id}/{arquivo_id}/extracao-preview` utiliza respostas simuladas e é restrita a acessos locais. Serve para demonstrar o fluxo de integração, mas não comprova o funcionamento do Gemini real.

O preview não substitui nem altera a integração real com o Gemini.

### Linux / macOS

```bash
sudo apt update
sudo apt install -y tesseract-ocr tesseract-ocr-por

git clone https://github.com/No-Country-simulation/G10-BRASIL-EQUIPO17.git
cd G10-BRASIL-EQUIPO17
git switch develop
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,ai,cloud]'
.venv/bin/python -m pytest -q
.venv/bin/python -m uvicorn mediflow.api.app:app --reload
```

## Mapa do projeto

| Local | Responsabilidade |
|---|---|
| `src/mediflow/api/` | API FastAPI |
| `src/mediflow/ingestion/` | Recebimento e preparação dos documentos (planejado) |
| `src/mediflow/extraction/` | Extração de dados por IA (planejada) |
| `src/mediflow/rag/` | Consulta à base de conhecimento (planejada) |
| `src/mediflow/agents/` | Orquestração do grafo (planejada) |
| `src/mediflow/storage/` | Integração OCI (planejada) |
| `src/mediflow/ui/` | Interface Streamlit (planejada) |
| `src/mediflow_contracts/` | Contratos Pydantic e motor inicial de decisões |
| `rules/` e `schemas/` | Regras YAML e JSON Schema gerados |
| `tests/` | Testes automatizados |
| `amostras/` e `exemplos/` | Entradas e saídas de demonstração, exclusivamente sintéticas |
| `docs/` e `diagramas/` | Arquitetura, decisões, fluxos e documentação histórica |

**Atenção:** `schemas/` é gerado a partir dos modelos Pydantic; execute `python scripts/exportar_schemas.py` em vez de editar os schemas manualmente.

## Guia para a equipe

- [CONTRIBUTING.md](CONTRIBUTING.md): nomes de branches, pull requests, testes e segurança.
- [docs/06_mapa_colaboracao.md](docs/06_mapa_colaboracao.md): módulos, papéis e nomes recomendados para entregas.
- [docs/01_arquitetura_monorepo.md](docs/01_arquitetura_monorepo.md): estrutura de software.
- [docs/02_git_colaboracao.md](docs/02_git_colaboracao.md): atalho para o guia Git atualizado.
- [docs/dia02/01_contrato_api.md](docs/dia02/01_contrato_api.md): contrato `v0.1`, referência técnica.
- [docs/03_plano_dia03.md](docs/03_plano_dia03.md): registro histórico de implantação inicial.

> Os nomes com `dia01`, `dia02` e `dia03` preservados **em artefatos históricos e testes existentes** não são exemplos para novas branches. As tags existentes também não precisam ser renomeadas.

## Próximas entregas por funcionalidade

1. `feat/oci-object-storage`: armazenamento privado OCI com teste real de upload/recuperação.
2. `feat/api-document-upload`: endpoint de ingestão PDF/PNG/JPEG, com validação.
3. `feat/ai-document-extraction`: leitura, classificação e extração estruturada.
4. `feat/rag-knowledge-retrieval`: recuperação de referências auditáveis.
5. `feat/rules-routing-engine` e `feat/agent-langgraph-workflow`: decisões condicionais em execução.
6. `feat/ui-document-dashboard` e `feat/ui-human-review`: interface e auditoria.

Os nomes são **sugestões**, não branches já criadas. Comece a partir de `develop` e abra PR para `develop`.
