"""B-009: valida os PDFs originais sintéticos, sem LLM ou credenciais.

Esses testes são intencionalmente exigentes: se o texto do DOC-002 não
contiver marcador explícito detectável, o I4 NÃO deve ser homologado.
"""
from hashlib import sha256
from pathlib import Path

from mediflow.extraction.port import DocumentoParaExtracao
from mediflow.rules.confirmador_alerta import ConfirmadorAlertaOriginal

RAIZ = Path(__file__).resolve().parents[1]


def _original(nome: str, doc_id: str) -> DocumentoParaExtracao:
    origem = RAIZ / "amostras" / "pdf" / nome
    conteudo = origem.read_bytes()
    return DocumentoParaExtracao(
        documento_id=doc_id, arquivo_id="a" * 32,
        nome_original=origem.name, mime_type="application/pdf",
        conteudo=conteudo, sha256=sha256(conteudo).hexdigest(),
    )


def test_doc001_pdf_sem_alerta_expresso_nao_dispara_r001():
    documento = _original("DOC-001_laudo_laboratorial_rotina.pdf", "DOC-001")
    assert ConfirmadorAlertaOriginal().confirmar(documento) is False


def test_doc002_pdf_com_alerta_expresso_deve_disparar_r001():
    documento = _original("DOC-002_laudo_imagem_alerta.pdf", "DOC-002")
    assert ConfirmadorAlertaOriginal().confirmar(documento) is True
