# Associação persistente entre documentos e objetos OCI

## Objetivo

Preservar o nome original de cada documento **sintético**, sem trocar a chave única usada no OCI Object Storage. A cada envio aceito pelo `POST /v1/triagens/arquivos`, o MediFlow grava **dois objetos** no bucket privado:

| Objeto | Exemplo | Conteúdo |
| --- | --- | --- |
| Original | `originais/DOC-001/<arquivo_id>.pdf` | PDF exatamente como recebido |
| Manifesto | `metadados/DOC-001/<arquivo_id>.json` | Identificação, nome original, chave do original, MIME, SHA-256, tamanho e data UTC |

`arquivo_id` é um UUID4 em hexadecimal. Dois uploads com o mesmo `documento_id` não se sobrescrevem.

**Escopo:** associação do **original**, não do resultado clínico, interpretação por IA, decisão de roteamento ou histórico de triagem. O contrato existente `ResultadoTriagem.armazenamento_oci` **não** é marcado como `confirmado`, pois exige original, resultado e histórico completos. O recibo continua com `status: recebido` e `triagem_executada: false`.

## Resposta do upload

Um upload bem-sucedido responde HTTP **201** com um recibo, inclusive:

```json
{
  "contrato_versao": "0.1",
  "documento_id": "DOC-001",
  "arquivo_id": "<uuid4-hex>",
  "registrado_em_utc": "2026-10-28T12:00:00Z",
  "status": "recebido",
  "entrada": {
    "tipo_entrada": "pdf",
    "canal_origem": "teste_sintetico",
    "sha256": "<sha256-hex-do-original>",
    "nome_arquivo": "DOC-001_laudo_laboratorial_rotina.pdf"
  },
  "armazenamento_original": {
    "status": "confirmado",
    "bucket": "mediflow-docs-dev",
    "chave_original": "originais/DOC-001/<uuid4-hex>.pdf"
  },
  "registro_metadados": {
    "status": "confirmado",
    "chave_metadados": "metadados/DOC-001/<uuid4-hex>.json"
  },
  "triagem_executada": false,
  "tamanho_bytes": 45200
}
```

O JSON é ilustrativo. O upload salva esse próprio recibo em UTF-8 como manifesto; a API só devolve HTTP 201 quando **as duas gravações** retornam SHA-256 correspondente ao conteúdo enviado.

## Consultar posteriormente

Existe um novo endpoint local de desenvolvimento:

```http
GET /v1/triagens/arquivos/{documento_id}/{arquivo_id}
```

Exemplo: após fazer upload pelo Swagger, copie `arquivo_id` da resposta e solicite `GET /v1/triagens/arquivos/DOC-001/<arquivo_id>`. Mesmo em uma nova requisição ou após reiniciar o servidor, a API busca o manifesto **na OCI** e devolve o nome original e a chave do arquivo. A operação não precisa de memória local.

A consulta é restringida pela mesma condição do upload: `MEDIFLOW_ENV=development`, `MEDIFLOW_ENABLE_LOCAL_UPLOADS=true` e acesso por `127.0.0.1`/`::1`. **Não disponibilize esses endpoints em rede pública**. A autenticação/autorização real ainda não foi implementada.

### Listar uploads de um `documento_id`

A listagem também está disponível, sem precisar conhecer previamente cada `arquivo_id`:

```http
GET /v1/triagens/arquivos/DOC-001?limite=20
```

A API utiliza a operação `list_objects` da OCI com o prefixo `metadados/DOC-001/`, valida as chaves encontradas e lê somente os manifestos JSON. **Não baixa os PDFs ou imagens originais** para produzir a listagem.

Exemplo de resposta **ilustrativa**:

```json
{
  "documento_id": "DOC-001",
  "quantidade_pagina": 2,
  "arquivos": [
    {
      "arquivo_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "nome_original": "laudo.pdf",
      "tipo_entrada": "pdf",
      "tamanho_bytes": 14520,
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "registrado_em_utc": "2026-10-28T12:00:00Z"
    },
    {
      "arquivo_id": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "nome_original": "receita.png",
      "tipo_entrada": "png",
      "tamanho_bytes": 2048,
      "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "registrado_em_utc": "2026-10-28T12:15:00Z"
    }
  ],
  "proximo_cursor": null
}
```

- `limite`: quantidade por página, de 1 a 50; padrão 20.
- `quantidade_pagina`: **não** é o total de registros existentes no bucket, apenas o número desta resposta.
- `proximo_cursor`: valor para a requisição seguinte, se houver outra página; `null` indica o fim.
- Para prosseguir, execute `GET /v1/triagens/arquivos/DOC-001?limite=20&cursor=<proximo_cursor>`. Quando usar ferramentas HTTP, informe `cursor` como parâmetro de consulta (a ferramenta codificará `/` e outros caracteres, se necessário).
- Documento sem manifestos: HTTP 200 com `arquivos: []`, `quantidade_pagina: 0` e `proximo_cursor: null`.
- `documento_id` incorreto: HTTP 422; cursor de outro documento ou inválido: HTTP 422.
- Falha da OCI ou inconsistência em um manifesto: HTTP 502 com erro genérico, sem retornar uma lista parcial como se fosse completa.
- O endpoint permanece **somente para desenvolvimento local**, protegido pela mesma condição do upload e do GET individual. Não expor publicamente sem autenticação/autorização.
- A listagem recupera **somente uploads que têm manifestos válidos**. Objetos criados antes da associação (ou originais órfãos após falha) não aparecem automaticamente.

Este recurso é uma listagem por prefixo no Object Storage, **não** um banco de dados, índice de busca por paciente nem listagem de resultados clínicos de triagem. A ordenação acompanha as chaves de objetos retornadas pela OCI, e não necessariamente a data de recebimento. Um índice persistente para consultas avançadas pode ser criado em outra etapa.

## Falhas e segurança

- Falha do upload original ou hash divergente: HTTP 502; manifesto não é gravado.
- Falha na gravação ou hash do manifesto: HTTP 502; **o original pode permanecer órfão no bucket**. Não é apagado automaticamente. Requer conferência e conciliação administrativa; não declarar sucesso falso.
- Manifesto não encontrado: HTTP 404.
- Manifesto corrompido ou com identificadores divergentes: HTTP 502 sem expor conteúdo ou segredo.
- Cada registro contém apenas os metadados necessários; não incluir extrações clínicas ou conteúdo do documento no manifesto.
- Uma chave OCI única não é controle de acesso. O bucket é privado, as permissões são IAM e a API requer autenticação real antes de exposição pública.
- Apenas dados sintéticos; nunca enviar arquivos reais de pacientes nesta fase.

**Aviso sobre uploads anteriores:** objetos enviados **antes** da implementação do manifesto não ganham associação retroativa. Devem ser registrados explicitamente ou reenviados após a atualização. Não reconstruir o nome original a partir do UUID da chave.

## Executar os testes

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
```

Os testes automatizados usam um armazenamento falso e não necessitam de credenciais Oracle. Para confirmar persistência real, faça upload no Swagger, obtenha `arquivo_id`, consulte o GET e verifique **dois objetos** no bucket privado (`originais/` e `metadados/`).
