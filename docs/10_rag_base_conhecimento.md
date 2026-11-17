# RAG: base de conhecimento e recuperação de referências (I3)

## O que é

Módulo que recupera e cita fichas da base de conhecimento do MediFlow. Ele entrega **referências com fonte**; não decide nada. A execução das condições, a precedência e os destinos das regras continuam sendo do motor determinístico do I4. A base não contém protocolo clínico: qualquer protocolo de prioridade precisa ser selecionado e validado por profissional habilitado antes de entrar (roteiro, item 5.3).

## Como usar (para I1 e I4)

```python
from mediflow.rag.carregador import criar_recuperador_padrao
from mediflow.rag.port import ConsultaRAG

recuperador = criar_recuperador_padrao()  # criar uma vez, na inicialização
resultado = recuperador.buscar(ConsultaRAG(texto="receituario sem dose legivel", limite=3))
```

O retorno é um `RecuperacaoRAG` (contrato v0.1, `mediflow_contracts.models`):

| status | fontes | quando |
|---|---|---|
| `consultado` | 1 ou mais | a busca achou fichas; cada `FonteRAG` traz `fonte_id`, `titulo`, `versao` e `trecho_relevante` |
| `sem_resultados` | vazia | a busca rodou e não achou nada; nenhuma fonte é inventada |
| `falha` | vazia | erro interno na busca, com `erro_codigo` (`RAG_ERRO_BUSCA`) |
| `nao_consultado` | vazia | valor padrão do contrato, para quando o RAG não foi chamado |

`criar_recuperador_padrao()` lê os arquivos da base. Se a base estiver inválida ou ausente, ele **levanta exceção** (`ValueError` ou `FileNotFoundError`); quem integra deve tratar isso, por exemplo registrando `status="falha"` no resultado.

## Onde ficam as fontes

`src/mediflow/rag/base_conhecimento/`, um arquivo `.md` por ficha, com cabeçalho:

```
---
fonte_id: R001
titulo: Título da ficha
versao: 0.1
origem: rules/roteamento.yaml
url: (opcional)
---
Texto da ficha.
```

O carregador rejeita ficha sem cabeçalho, sem `fonte_id`, `titulo` ou `versao`, com texto vazio ou com `fonte_id` repetido. Para ampliar a base, basta adicionar um arquivo, sem mexer no código de busca.

## Fichas atuais

- Regras de roteamento R001 a R006 e a precedência (origem: `rules/roteamento.yaml`).
- Validações V001 a V004 e campos mínimos por categoria (origem: `rules/validacao.yaml`).
- Ficha do tipo de documento "receituário".
- Status dos campos extraídos (origem: `mediflow_contracts/models.py`).

## Origem da ficha e url

Cada ficha guarda a origem em `origem:` e o link navegável do arquivo-fonte em `url:`. O carregador lê o campo e o recuperador o devolve em `FonteRAG.url`, sem alterar o contrato `RecuperacaoRAG` v0.1 e sem colocar prefixo no `trecho_relevante`. Fichas das regras apontam para `rules/roteamento.yaml` ou `rules/validacao.yaml`; fontes externas futuras entram com o link oficial. O teste `tests/test_rag_url_origem.py` confere a propagação.

## Sincronia com os YAMLs

Os YAMLs de `rules/` são a referência oficial. O arquivo `tests/test_rag_sincronia_yaml.py` falha quando uma ficha diverge deles (IDs, versão, precedência, revisão humana e campos mínimos). Se alguém mudar uma regra, o teste indica qual ficha atualizar.

## Limites atuais

- Busca por palavras-chave, sem embeddings nem banco vetorial.
- Ainda não está integrado à API nem ao LangGraph.
- A base ainda não tem fontes oficiais externas (por exemplo, guia da receita e tabela CID-10); elas entram como sínteses da equipe, com título, versão e link.
- Somente dados sintéticos.
