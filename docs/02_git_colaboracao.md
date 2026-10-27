# Git e colaboração — Guia atualizado

A convenção vigente do MediFlow está centralizada em **[CONTRIBUTING.md](../CONTRIBUTING.md)**. Este arquivo permanece para manter compatibilidade com links do roteiro anterior.

## Resumo

- `main`: versão estável; `develop`: integração.
- Branches temporárias: `feat/area-funcionalidade`, `fix/area-problema`, `docs/assunto`, `test/escopo`, `refactor/escopo`, `chore/escopo`.
- **Não usar nomes de dias, semanas, datas ou integrantes em branches.**
- Trabalhar em branch individual criada a partir da `develop`, com Pull Request para `develop`, pelo menos uma revisão e CI aprovada.
- Evitar `push` direto e reescrita de histórico nas branches compartilhadas.

## Repositório oficial

https://github.com/No-Country-simulation/G10-BRASIL-EQUIPO17

```powershell
git clone https://github.com/No-Country-simulation/G10-BRASIL-EQUIPO17.git
cd G10-BRASIL-EQUIPO17
git switch develop
```

Consulte [CONTRIBUTING.md](../CONTRIBUTING.md) para instalação, testes, comandos de branch e critérios do PR.

> As instruções antigas de clonagem de ZIP/bundle pertencem ao registro histórico de implantação inicial e **não** devem ser utilizadas por novos integrantes.
