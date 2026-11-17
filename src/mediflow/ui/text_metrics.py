"""
Largura aproximada de texto na fonte das células do st.dataframe (Inter 400, 13,125 px).

O grid desenha num canvas e só alinha células à esquerda/centro/direita. Para centrar um
bloco de valores alinhados à esquerda entre si, a vista mede o texto aqui e acrescenta
espaços não separáveis à frente. Larguras medidas no navegador com canvas.measureText.
"""

NBSP = " "

# Largura de cada carácter (px). Caracteres em falta usam a média.
CHAR_PX = {
    " ": 3.69, "'": 3.93, "(": 4.79, ")": 4.79, ",": 3.78, "-": 6.03, ".": 3.78, "/": 4.73,
    "0": 8.28, "1": 5.34, "2": 8, "3": 8.1, "4": 8.48, "5": 7.78, "6": 8.14, "7": 7.42, "8": 8.12,
    "9": 8.14, ":": 3.78, "A": 9.05, "B": 8.58, "C": 9.58, "D": 9.47, "E": 7.89, "F": 7.75,
    "G": 9.79, "H": 9.75, "I": 3.52, "J": 7.49, "K": 8.81, "L": 7.42, "M": 11.85, "N": 9.88,
    "O": 10.03, "P": 8.38, "Q": 10.03, "R": 8.44, "S": 8.42, "T": 8.47, "U": 9.76, "V": 9.05,
    "W": 12.93, "X": 8.95, "Y": 8.9, "Z": 8.25, "a": 7.37, "b": 8.03, "c": 7.5, "d": 8.03,
    "e": 7.65, "f": 4.86, "g": 8.05, "h": 7.76, "i": 3.18, "j": 3.18, "k": 7.2, "l": 3.18,
    "m": 11.49, "n": 7.75, "o": 7.87, "p": 8.03, "q": 8.03, "r": 4.94, "s": 6.93, "t": 4.29,
    "u": 7.76, "v": 7.37, "w": 10.74, "x": 7.16, "y": 7.37, "z": 7.25, NBSP: 3.69, "·": 3.78,
    "À": 9.05, "Á": 9.05, "Â": 9.05, "Ã": 9.05, "Ç": 9.58, "É": 7.89, "Ê": 7.89, "Í": 3.52,
    "Ó": 10.03, "Ô": 10.03, "Õ": 10.03, "Ú": 9.76, "à": 7.37, "á": 7.37, "â": 7.37, "ã": 7.37,
    "ä": 7.37, "ç": 7.5, "è": 7.65, "é": 7.65, "ê": 7.65, "ë": 7.65, "ì": 3.18, "í": 3.18,
    "î": 3.18, "ï": 3.18, "ñ": 7.75, "ò": 7.87, "ó": 7.87, "ô": 7.87, "õ": 7.87, "ö": 7.87,
    "ù": 7.76, "ú": 7.76, "û": 7.76, "ü": 7.76,
    # Pontos coloridos de prioridade e estado (emoji).
    "🔴": 18.01, "🟠": 18.01, "🟢": 18.01, "⚪": 18.01, "🟣": 18.01, "🔵": 18.01, "🟡": 18.01,
    "⚫": 18.01,
}
_AVERAGE_PX = sum(CHAR_PX.values()) / len(CHAR_PX)
NBSP_PX = CHAR_PX[NBSP]


def text_width(text: str) -> float:
    return sum(CHAR_PX.get(ch, _AVERAGE_PX) for ch in str(text))


def centered_block_pad(values, column_px: float, left_pad_px: float = 8) -> str:
    """Espaços que, postos à frente de todos os valores, centram o bloco na coluna."""
    widest = max((text_width(v) for v in values), default=0)
    gap = (column_px - widest) / 2 - left_pad_px
    return NBSP * max(0, round(gap / NBSP_PX))
