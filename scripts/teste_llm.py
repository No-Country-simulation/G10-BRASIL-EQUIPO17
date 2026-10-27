import os
from google import genai

MODELO = "gemini-3.1-flash-lite"

cliente = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
resposta = cliente.models.generate_content(
    model=MODELO,
    contents="Responda apenas com a palavra: ok",
)
print(resposta.text)
