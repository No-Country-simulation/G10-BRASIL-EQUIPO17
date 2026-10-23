"""Gera esquemas a partir da fonte canônica Pydantic."""
from pathlib import Path
import json, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from mediflow_contracts.models import EntradaTexto, ExtracaoIA, ResultadoTriagem
for nome, modelo in [
    ('entrada_texto.schema.json',EntradaTexto),
    ('extracao_ia.schema.json',ExtracaoIA),
    ('resultado_triagem.schema.json',ResultadoTriagem)
]:
    (ROOT/'schemas'/nome).write_text(
        json.dumps(modelo.model_json_schema(),ensure_ascii=False,indent=2)+'\n', encoding='utf-8'
    )
print('3 schemas JSON v0.1 exportados')
