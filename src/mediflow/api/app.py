"""API inicial (Dia 3). Nao realiza inferencia, triagem ou armazenamento."""
from fastapi import FastAPI, HTTPException
from mediflow_contracts.models import EntradaTexto
from mediflow.api.uploads import router as uploads_router
from mediflow.api.extraction_preview import router as extraction_preview_router

app = FastAPI(
    title="MediFlow — API de desenvolvimento",
    version="0.1.0",
    description=(
        "Protótipo educacional com dados sintéticos. "
        "No Dia 3, apenas infraestrutura e validação de contratos. "
        "Não utilizar para decisões clínicas."
    ),
)


@app.get("/health", tags=["infraestrutura"])
def health() -> dict[str, str]:
    """Disponibilidade da API; NAO comprova que IA/OCI estao disponiveis."""
    return {"status": "ok", "servico": "mediflow", "modo": "esqueleto_dia03", "contrato_versao": "0.1"}


@app.post("/v1/triagens/texto", tags=["triagem"])
def criar_triagem_texto(entrada: EntradaTexto) -> None:
    """Valida entrada, mas nao finge processamento que ainda nao existe."""
    raise HTTPException(
        status_code=501,
        detail={"codigo": "TRIAGEM_NAO_IMPLEMENTADA", "mensagem": "Fluxo de ingestao previsto para o Dia 5."},
    )


# Ingestão restrita ao desenvolvimento local; autenticação será implementada antes do deploy.
app.include_router(uploads_router)

# Preview de integração I1/I2, sempre simulado e restrito a localhost.
app.include_router(extraction_preview_router)
