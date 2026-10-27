## Objetivo da alteração

Descreva o que muda e por que a mudança é necessária.

## Identificação
- Issue / backlog:
- Integrante responsável:
- Revisor de outra área:
- Branch de origem: `feat/area-funcionalidade` (ou `fix/`, `docs/`, `test/`, `refactor/`, `chore/`)
- Branch de destino: `develop` (exceção: promoção revisada de `develop` para `main`)

## Verificações
- [ ] Nome da branch descreve a funcionalidade (sem dia, semana, data ou nome de integrante)
- [ ] Testes locais: `python -m pytest -q`
- [ ] Sintaxe: `python -m compileall -q src scripts tests`
- [ ] CI do GitHub aprovada
- [ ] Contratos JSON v0.1 preservados ou alterações versionadas e explicadas
- [ ] Nenhum dado real de paciente, chave, token ou segredo no PR
- [ ] Mudanças e possíveis efeitos sobre outras áreas explicados

## Evidências e riscos

Inclua resultados de testes, capturas relevantes ou exemplos sintéticos, se aplicável.
