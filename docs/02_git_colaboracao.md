# Estratégia de Git e colaboração — Dia 3

## Branches
- `main`: versões estáveis demonstráveis. Sem push direto na rotina da equipe.
- `develop`: integração de funcionalidades que passaram testes.
- `feat/dia04-oci`: exemplo de branch para I5, aberta a partir de `develop`.
- Demais atividades: `feat/<id-backlog>-descricao`, `fix/<descricao>`, `docs/<descricao>`.

## Pull request
1. Atualize `develop` e crie `feat/...` a partir dela.
2. Faça commits pequenos e objetivos; inclua ID do backlog no título.
3. Rode `python -m pytest -q` e `python -m compileall -q src scripts tests`.
4. Abra PR para `develop`; pelo menos um revisor de outra área valida contratos/efeitos colaterais.
5. Após aprovação e CI verde, merge via PR. Evitar alteração manual de schemas gerados.
6. Ao fechar marco semanal, PR de `develop` para `main` + tag, por exemplo `v0.1.0-dia03`.

## Inicialização em Windows PowerShell
```powershell
git clone .\MediFlow_Dia03.bundle MediFlow
cd MediFlow
git branch -a
git switch develop
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn mediflow.api.app:app --reload
```
A API estará em `http://127.0.0.1:8000/docs`, quando o servidor for iniciado.

> O bundle Git é um snapshot **local**, sem remote GitHub. Para publicar, crie um repositório privado ou público conforme decisão da equipe e use `git remote add origin <url>`; após isso, `git push -u origin main develop`.

## Caso use o ZIP em vez do bundle
```powershell
Expand-Archive .\MediFlow_Dia03.zip -DestinationPath .
cd .\MediFlow_Dia03
git init -b main
git add .
git commit -m "chore: base do Dia 3"
git switch -c develop
```
A criação de branches remotas e as proteções só poderão ser confirmadas no GitHub após publicar o repositório.
