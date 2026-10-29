# Ingestão de arquivos na FastAPI — integração com OCI (I1/I5)

## Objetivo e limitações

O endpoint `POST /v1/triagens/arquivos` recebe um arquivo **sintético** em `multipart/form-data`, valida tamanho, formato e assinatura, envia o original ao `OCIStorage` e retorna um **recibo de armazenamento** HTTP 201.

**Não realiza triagem clínica, LLM, RAG ou roteamento.** `status=recebido` e `triagem_executada=false`. Após a inclusão da associação persistente, a API grava também um manifesto JSON por upload; veja [08_associacao_metadados_oci.md](08_associacao_metadados_oci.md). O campo `armazenamento_original.status=confirmado` se refere **somente ao original**. Não utilizar `ResultadoTriagem.armazenamento_oci.status=confirmado`, pois no contrato v0.1 esse estado requer também os objetos de resultado e histórico; estes ainda não existem.

## Restrições iniciais

- Formatos: PDF (`application/pdf`), PNG (`image/png`), JPEG (`image/jpeg`). Extensão, MIME e assinatura devem corresponder.
- Limite: 10 MiB por arquivo, leitura em blocos de 1 MiB; PDF com até 10 páginas e legível pelo `pypdf`.
- Além da assinatura, PNG/JPEG passam pela decodificação e verificação com Pillow. Mesmo assim, isso **não equivale a uma análise antivírus**.
- Nome informado pelo cliente é sanitizado e usado **apenas em metadados**. A chave OCI usa `originais/<documento_id>/<uuid>.<ext>` para evitar sobrescrita.
- Não há autorização, antivírus, controle de duplicatas, **índice de listagem por documento** ou serviço remoto nesta entrega. A associação individual original/manifesto é persistida e consultável por `documento_id` e `arquivo_id`.

## Segurança do ambiente de desenvolvimento

O endpoint é **bloqueado por padrão**, inclusive no Swagger. Para testar localmente, use no PowerShell:

```powershell
$env:MEDIFLOW_ENV="development"
$env:MEDIFLOW_ENABLE_LOCAL_UPLOADS="true"
$env:OCI_CONFIG_FILE="$HOME\.oci\config"
$env:OCI_CONFIG_PROFILE="MEDIFLOW"
$env:OCI_BUCKET="mediflow-docs-dev"
.\.venv\Scripts\python.exe -m pip install -e '.[dev,cloud]'
.\.venv\Scripts\python.exe -m uvicorn mediflow.api.app:app --reload --host 127.0.0.1
```

Abra `http://127.0.0.1:8000/docs`, selecione `POST /v1/triagens/arquivos`, clique em **Try it out** e preencha `documento_id` (ex.: `DOC-001`), `canal_origem` (`teste_sintetico`) e `arquivo` (PDF, PNG ou JPEG de `amostras/`). A resposta esperada é **201**, com `status=recebido`, `triagem_executada=false` e o identificador de armazenamento do original.

O bloqueio por IP é um **mecanismo de segurança apenas auxiliar**, não uma solução de autenticação. Nunca exponha o servidor ou rode em `0.0.0.0` com esta configuração; implemente autenticação/autorização real antes de qualquer deploy.

## Testes automatizados

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
```

Os testes do endpoint usam `app.dependency_overrides` com storage simulado; não acessam a OCI nem requerem chave privada.

## Tratamento de falhas

- `400`: nome ausente/inválido ou arquivo vazio.
- `415`: formato não permitido, MIME ou assinatura incompatível.
- `413`: mais de 10 MiB ou PDF acima de 10 páginas.
- `422`: campos inválidos, PDF ilegível ou imagem inválida.
- `403`: endpoint de desenvolvimento desativado ou cliente não local.
- `503`: configuração OCI indisponível.
- `502`: upload remoto não confirmado.

O corpo de erros de armazenamento é genérico para não expor exceções da Oracle, caminhos de chaves ou credenciais.

## Próximos marcos

1. Autenticação/autorização e rate limiting; incluir controles antimalware e limites adicionais de abuso.
2. Criar índice/listagem por documento, persistir resultados e histórico da triagem. O manifesto individual do upload já é persistido.
3. Vincular à extração multimodal, regras, LangGraph, RAG e auditoria, sem mudar o significado do recibo.
