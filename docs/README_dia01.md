# MediFlow — Entrega do Dia 1: requisitos, backlog e demonstrações

**Data da preparação:** 22/10/2026  
**Equipe:** 6 integrantes (I1 a I6) | **Prazo planejado:** 5 semanas / 25 dias úteis  
**Estado:** análise inicial preparada pelo Integrante Universal; **aprovação coletiva pendente**.

## Propósito
Esta entrega converte o **edital `MediaFlow_Hackathon.pdf` (título oficial MediFlow)** em um backlog priorizado, uma taxonomia inicial de documentos e critérios verificáveis para os três cenários oficiais. **Não há aplicação implementada neste pacote.**

## Abrir primeiro
1. `docs/01_requisitos_e_escopo.md`: o que o edital obriga e o que foi acrescentado por decisão de engenharia.
2. `docs/02_backlog_priorizado.md` e `dados/backlog.csv`: histórias de usuário, prioridade, dependências, responsáveis e prazos.
3. `docs/03_catalogo_documental.md` e `dados/categorias.json`: categorias, campos e comportamento quando faltarem informações.
4. `docs/04_cenarios_e_criterios.md` e `dados/cenarios.json`: entradas de teste, gabaritos e regras de aceitação.
5. `docs/05_plano_semana1.md`: distribuição por dia e por integrante.
6. `docs/06_decisoes_riscos.md`: decisões propostas, riscos e pendências para o Dia 2.

## Dados de teste
`amostras/` contém cópias **exatas** dos três arquivos sintéticos do `MediFlow_Kit_Hackathon.zip`: DOC-001 (rotina), DOC-002 (urgência expressa), DOC-005 (dosagem ilegível). `dados/gabarito_tres_cenarios.json` contém apenas a referência de testes, que **NÃO** deve ser enviada à LLM nem indexada no RAG.

## Como validar o pacote

```bash
python testes/verificar_entrega.py
```

Esse comando utiliza apenas a biblioteca padrão do Python e verifica referências, exclusividade de IDs, três cenários, arquivos e hashes. Ele **não** testa a IA, a OCI ou a lógica clínica, ainda não implementadas.

## O que faremos no Dia 2
Formalizar o **contrato JSON v0.1**, versionar o schema, definir campos obrigatórios por tipo e desenhar o grafo do LangGraph (ainda sem execução). O catálogo e os roteamentos deste Dia 1 são **propostas de escopo**, não critérios médicos normativos.

## Fontes
- Fonte primária: `MediaFlow_Hackathon.pdf`, páginas 1–6 (fornecido pela equipe).
- Material sintético já criado: `MediFlow_Kit_Hackathon.zip`, especialmente `expected/gabarito.json` e `rules/roteamento.yaml` (regras locais fictícias).
- Nenhuma consulta a pacientes ou prontuários reais. Não foi feita validação clínica nem conformidade regulatória certificada.
