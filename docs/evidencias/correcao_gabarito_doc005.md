# Correção do gabarito de extração — DOC-005

## Justificativa

A conferência visual do documento original DOC-005 confirmou que a data de emissão, o nome do profissional prescritor e o CRM estão legíveis.

Os arquivos `exemplos/DOC-005_extracao_ia.json` e `exemplos/DOC-005_resultado.json` foram atualizados para refletir fielmente essas informações:

- Nome: Dr. André Lima Exemplo
- CRM: CRM-XX 000005
- Data de emissão: 20/10/2026 (normalizada para 2026-10-20)

## Campo intencionalmente ilegível

A dosagem do medicamento permanece `null`, com `dosagem_status="ilegivel"`, pois não é possível confirmá-la visualmente no documento original.

## Encaminhamento

O encaminhamento para auditoria humana foi preservado:
- Regra principal: R002
- Destino: auditoria humana
- Revisão humana obrigatória: true

## Escopo e regressão

A correção não altera referências históricas de `baseline_dia1`.

O teste `tests/test_doc005_gabarito.py` verifica os campos legíveis, as evidências, a dosagem ilegível e a preservação do encaminhamento R002.
