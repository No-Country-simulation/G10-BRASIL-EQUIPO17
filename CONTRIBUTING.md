# Guia de colaboração do MediFlow

## 1. Branches: nomenclatura oficial

**Formato:** `tipo/area-funcionalidade`, com letras minúsculas, números e hífens ASCII. O nome descreve **o que será entregue**, não quem executa ou quando executa.

| Prefixo | Uso | Exemplo |
|---|---|---|
| `feat/` | Funcionalidade | `feat/oci-object-storage` |
| `fix/` | Correção de falha | `fix/invalid-pdf-upload` |
| `docs/` | Documentação | `docs/branch-naming-policy` |
| `test/` | Testes | `test/routing-scenarios` |
| `refactor/` | Refatoração | `refactor/agent-workflow` |
| `chore/` | Configuração/manutenção | `chore/python-dependencies` |

**Não usar:** `feat/dia04-oci`, `feat/semana2`, `feature/extracao-base` em novas branches, `feat/integrante3` ou datas no nome. Branches históricas e tags antigas não precisam ser reescritas.

**Branches permanentes:** `main` é a versão estável e `develop` é a integração. Nunca trabalhar diretamente nelas. Uma funcionalidade = uma branch de duração limitada e um PR.

## 2. Procedimento por funcionalidade

Antes de começar, confirme que o trabalho está no backlog/Issue e verifique dependências com outros integrantes.

```powershell
git switch develop
git pull --ff-only origin develop
git switch -c feat/oci-object-storage
```

Substitua o nome da branch pela entrega em execução. Antes de enviar o código:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
git status
# Revise todos os arquivos listados. Não inclua segredos, .env nem dados clínicos reais.
git add -A
git commit -m "feat(oci): implementar armazenamento privado"
git push -u origin feat/oci-object-storage
```

Abra um **Pull Request com base `develop`**, vinculando o Issue (quando existir), descrevendo testes, riscos e alterações nos contratos. Solicite revisão de ao menos um integrante de outra área. Aguarde CI aprovada antes do merge.

Após um marco estável, a equipe abre **PR de `develop` para `main`**. Tags de release futuras podem usar SemVer, por exemplo `v0.2.0`.

## 3. Regras da equipe

- Não fazer `git push --force` nem reescrever histórico compartilhado.
- Não enviar código diretamente para `main` ou `develop` no fluxo normal.
- Não fazer merge de trabalho ainda não revisado.
- Sempre incluir testes quando houver mudança funcional.
- Se alterar contratos, versionar a mudança, revisar compatibilidade e regenerar os schemas com `python scripts/exportar_schemas.py`.
- Não adicionar `.env`, credenciais da Oracle, chaves privadas, tokens de LLM, dados reais de pacientes ou arquivos de produção ao Git.
- Preferir dados sintéticos dos cenários oficiais de teste.

## 4. Dependências e histórico

- [Módulos e branches sugeridas](docs/06_mapa_colaboracao.md)
- [Contrato API](docs/dia02/01_contrato_api.md)
- [Arquitetura](docs/01_arquitetura_monorepo.md)

Arquivos com `diaXX` em caminhos históricos (ex.: `baseline_dia1/`, `docs/dia02/`) são **registros já aprovados**, não nomes de branches; não renomeá-los sem planejar as mudanças em testes e documentação.

### Branches antigas e PRs

- Caso exista uma branch antiga com prefixo `feature/`, não a delete ou renomeie enquanto alguém estiver desenvolvendo nela sem consultar seu responsável.
- Para PR já **mesclado**, confirme com o autor que a branch não está mais em uso e use a opção **Delete branch** do GitHub; os commits e o PR continuam preservados.
- Se alguma alteração foi integrada à `main`, mas ainda não à `develop`, primeiro sincronize as branches com PR `main` → `develop`, sem `push --force`.
