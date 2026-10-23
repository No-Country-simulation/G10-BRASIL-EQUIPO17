# Dia 2 — Contrato de API e dados `v0.1`

## Regra de compatibilidade
`src/mediflow_contracts/models.py` é a **fonte canônica** dos tipos. A pasta `schemas/` é gerada por `python scripts/exportar_schemas.py` e não deve ser editada manualmente. Campos fora do contrato geram erro (`extra=forbid`).

## 1. API para texto (a implementar a partir do Dia 3)
- `POST /v1/triagens/texto` com `Content-Type: application/json`, corpo validado pelo `entrada_texto.schema.json`.
- `POST /v1/triagens/arquivos` com `multipart/form-data`: campos `documento_id`, `canal_origem` e `arquivo` binário (PDF/PNG/JPEG). **Não colocar base64 do arquivo dentro do JSON**.
- `GET /v1/triagens/{documento_id}` consulta resultado/histórico, desde que o ID pertença ao escopo autorizado (autenticação planejada).
- Resposta sincrônica proposta: `200` ao concluir a triagem ou um erro estruturado; `202` somente se houver processamento assíncrono implementado. **Nenhum endpoint ainda existe no Dia 2.**
- Limite inicial **proposto**, sujeito a validação: arquivos de até 10 MiB e PDFs de até 10 páginas; validar MIME, assinatura e tamanho. Texto limitado a 100.000 caracteres.

## 2. Três contratos JSON
| Contrato | Arquivo | Função |
|---|---|---|
| Entrada de texto | `schemas/entrada_texto.schema.json` | Validar JSON enviado pelo cliente |
| Extração da IA | `schemas/extracao_ia.schema.json` | Normalizar campos; não aceitar dados livres como resultado definitivo |
| Resultado da triagem | `schemas/resultado_triagem.schema.json` | Interface comum entre back-end, UI, armazenador e fila |

## 3. Campos de saída
- `documento_id`, `contrato_versao`, `status` (`recebido`, `processando`, `processado`, `aguardando_auditoria`, `falha`).
- `entrada`: tipo de arquivo, origem, hash SHA-256 somente quando apurado, nome quando conhecido.
- `classificacao`: uma das sete categorias estáveis, prioridade documental (`rotina`, `possivel_urgencia`, `indeterminada`), indicador documental não calibrado (`valor=null` enquanto não calculado).
- `dados_extraidos`: paciente, profissional, exame, resultados, medicamentos, guias, datas e outros campos por categoria. `null` significa informação desconhecida; não inventar valores.
- `validacao`: ausências, ilegibilidades, conflitos e integridade administrativa.
- `evidencias`: trecho literal do documento, nome do campo e página 1-based (se conhecida); nunca usar texto do RAG como prova de campo presente no documento.
- `rag`: status e referências quando consultado. Recuperação não dita rota final.
- `decisao_roteamento`: destino principal, necessidade de revisão, regra principal e **todas as regras disparadas**.
- `armazenamento_oci`: `pendente` por padrão; `confirmado` apenas após gravação comprovada do original, resultado e histórico. Nunca inventar bucket/chaves.
- `eventos`: auditabilidade, sem informações sensíveis nos logs.

## 4. Regras de significado
1. **Prioridade ≠ aprovação:** `possivel_urgencia` é alerta documental para humano, jamais diagnóstico.
2. **`aguardando_auditoria` ≠ erro:** o processamento terminou, mas a revisão ainda está pendente.
3. **`falha` ≠ rotina:** erros técnicos devem ser registrados como falha e roteados a uma fila técnica.
4. **Conflito**: se R001 e R002 dispararem, R001 é principal e R002 permanece em `regras_disparadas`.
5. **Métrica**: `indicador_qualidade.valor=null` até existir algoritmo efetivamente implementado. `calibrado=false` explicita que não é probabilidade de acerto.
6. **CID:** preencher apenas quando escrito no documento; nunca usar sugestão automática como diagnóstico confirmado.
7. **Datas**: usar ISO `YYYY-MM-DD` na estrutura, preservar o trecho original na evidência.
8. **CPF/CRM:** somente transcrição dos dados sintéticos, sem alegar validação profissional/cadastral.

## 5. Exemplo de rotas REST do Dia 3
```http
POST /v1/triagens/texto
Content-Type: application/json
```
Corpo no arquivo `exemplos/entrada_texto.json`. O exemplo não é uma chamada real.

## 6. Evolução compatível
O campo `contrato_versao` obriga negociação e detecção de versões diferentes. A equipe deverá versionar mudanças incompatíveis (`0.2`, futuramente `1.0`) sem sobrescrever a baseline `0.1`.
