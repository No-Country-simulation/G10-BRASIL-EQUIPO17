"""Página 2 — Enviar documento: ingestão de ficheiros ou texto livre."""

from __future__ import annotations

import time
from io import BytesIO
from pathlib import Path

import streamlit as st

from mediflow.ui.api_client import APIError, get_backend
from mediflow.ui.components import badge_row, page_header, priority_badge, show_api_error
from mediflow.ui.config import ACCEPTED_FILE_TYPES, FILE_SIGNATURES, MAX_PDF_PAGES, MAX_UPLOAD_MB
from mediflow.ui.models import normalize_document
from mediflow.ui.navigation import go_to

_MODES = {"file": ":material/upload_file: Arquivo", "text": ":material/notes: Texto livre"}

# O widget aceita ficheiros maiores do que o limite e de qualquer tipo, para que a validação
# (e a mensagem de erro exata, em português) seja feita aqui e não pelo Streamlit.
_UPLOAD_HARD_LIMIT_MB = 200
_UPLOAD_NONCE = "_upload_nonce"  # muda a key do widget para o esvaziar ("Remover")

# Modo texto: chaves de sessão, mínimo para parecer um documento e pistas do tipo de documento.
_TEXT_KEY, _TEXT_READ = "doc_text", "_doc_text_read"
_MIN_WORDS, _MIN_CHARS = 8, 40
_DOC_HINTS = [
    ("Receita médica", ("receita", "posologia", "comprimido", " mg", "tomar ", "uso oral")),
    ("Pedido de exames", ("exame", "solicito", "hemograma", "pedido", "ultrassom", "raio-x")),
    ("Relatório clínico", ("relatório", "diagnóstico", "alta", "antecedentes", "evolução")),
]

# Cores da área de envio por tema (o tema do Streamlit não estiliza o file_uploader a este nível).
_SURFACES = {
    "light": {"card": "#ffffff", "border": "#e6ebf1", "zone": "#fbfcfd", "dash": "#cbd5e1",
              "text": "#334155", "muted": "#94a3b8", "accent": "#0f766e", "accent_bg": "#f0fdfa",
              "accent_strong": "#ccfbf1", "track": "#e2e8f0",
              "shadow": "0 1px 2px rgba(15,23,42,.04), 0 8px 24px -12px rgba(15,23,42,.12)"},
    "dark": {"card": "#111a2e", "border": "#1e293b", "zone": "#0e1628", "dash": "#334155",
             "text": "#cbd5e1", "muted": "#64748b", "accent": "#2dd4bf", "accent_bg": "rgba(45,212,191,.06)",
             "accent_strong": "rgba(45,212,191,.16)", "track": "#1e293b",
             "shadow": "0 1px 2px rgba(0,0,0,.3)"},
}
_FILE_ICONS = {"pdf": ":material/picture_as_pdf:", "png": ":material/image:", "jpg": ":material/image:",
               "jpeg": ":material/image:"}


def _types_label() -> str:
    """'PDF, PNG ou JPG' a partir de ACCEPTED_FILE_TYPES (JPEG conta como JPG)."""
    types = ", ".join(t.upper() for t in ACCEPTED_FILE_TYPES if t != "jpeg")
    return " ou ".join(types.rsplit(", ", 1))


def _uploader_key() -> str:
    return f"doc_upload_{st.session_state.get(_UPLOAD_NONCE, 0)}"


def _reset_upload() -> None:
    st.session_state[_UPLOAD_NONCE] = st.session_state.get(_UPLOAD_NONCE, 0) + 1


def _format_mb(size_bytes: int) -> str:
    """Tamanho legível em português: KB abaixo de 1 MB, MB com uma casa decimal acima."""
    if size_bytes < 1024 * 1024:
        return f"{max(1, round(size_bytes / 1024))} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB".replace(".", ",")


def _validate(uploaded) -> tuple[str, str] | None:
    """Devolve (título, motivo) se o ficheiro não puder ser processado."""
    ext = Path(uploaded.name).suffix.lower().lstrip(".")
    if ext not in ACCEPTED_FILE_TYPES:
        shown = f".{ext}" if ext else "sem extensão"
        return ("Formato não suportado",
                f"«{uploaded.name}» é um arquivo {shown}. Envie um documento em {_types_label()}.")
    if uploaded.size == 0:
        return "Arquivo vazio", f"«{uploaded.name}» não tem conteúdo. Confira o arquivo e tente de novo."
    if uploaded.size > MAX_UPLOAD_MB * 1024 * 1024:
        return ("Arquivo muito grande",
                f"«{uploaded.name}» tem {_format_mb(uploaded.size)}. O limite é {MAX_UPLOAD_MB} MB por arquivo.")
    content = uploaded.getvalue()
    if not content.startswith(FILE_SIGNATURES.get(ext, (b"",))):
        return ("Conteúdo não corresponde à extensão",
                f"«{uploaded.name}» não parece ser um {ext.upper()} válido. Confira o arquivo e tente de novo.")
    if ext == "pdf":
        pages = _pdf_pages(content)
        if pages is None:
            return "PDF ilegível", f"Não foi possível abrir «{uploaded.name}». O arquivo pode estar corrompido."
        if pages > MAX_PDF_PAGES:
            return ("PDF com páginas demais",
                    f"«{uploaded.name}» tem {pages} páginas. O limite é {MAX_PDF_PAGES} páginas por PDF.")
    return None


def _pdf_pages(content: bytes) -> int | None:
    """Número de páginas do PDF; None se não abrir. Sem pypdf instalado, a contagem é ignorada (0)."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return 0
    try:
        return len(PdfReader(BytesIO(content)).pages)
    except Exception:  # noqa: BLE001 — qualquer erro de leitura significa PDF inválido
        return None


# --------------------------------------------------------------------------- #
# Estilos e comportamento da zona de envio
# --------------------------------------------------------------------------- #
def _styles() -> None:
    """Zona "drag and drop": tracejado grande, ícone em círculo, texto ao centro e estados visuais.

    Reaproveita o st.file_uploader nativo (seleção e arrastar e largar): o botão "Upload" fica
    invisível e estica-se sobre a zona inteira, para que todo o retângulo seja clicável, e os
    textos em inglês dão lugar aos textos abaixo. A lista de ficheiros do Streamlit é escondida:
    o estado de sucesso/erro é desenhado pela página.
    """
    s = _SURFACES["dark" if st.context.theme.type == "dark" else "light"]
    zone = "[class*='st-key-doc_upload'] [data-testid='stFileUploaderDropzone']"
    instr = f"{zone} [data-testid='stFileUploaderDropzoneInstructions']"
    st.html(f"""<style>
    .st-key-upload_card {{
        background: {s['card']}; border: 1px solid {s['border']} !important;
        border-radius: 1.1rem !important; box-shadow: {s['shadow']}; padding: 1.5rem !important;
    }}
    /* Estado vazio. */
    {zone} {{
        position: relative; display: flex; flex-direction: column; align-items: center;
        justify-content: center; gap: .35rem; min-height: 260px; padding: 2.5rem 1.5rem;
        background: {s['zone']}; border: 2px dashed {s['dash']}; border-radius: 1rem;
        transition: border-color .15s ease, background .15s ease, transform .15s ease;
    }}
    {zone}::before {{
        content: "upload"; font-family: "Material Symbols Rounded"; font-size: 30px; line-height: 1;
        width: 64px; height: 64px; display: grid; place-items: center; margin-bottom: .9rem;
        border-radius: 50%; border: 1px solid {s['border']}; background: {s['card']};
        color: {s['text']}; box-shadow: 0 1px 2px rgba(15,23,42,.06);
        transition: color .15s ease, border-color .15s ease, transform .15s ease;
    }}
    /* Botão nativo invisível por cima da zona inteira: clicar em qualquer ponto abre o seletor. */
    {zone} > span {{ position: absolute; inset: 0; margin: 0; }}
    {zone} > span button {{ width: 100%; height: 100%; opacity: 0; cursor: pointer; }}
    {instr} {{
        display: flex !important; flex-direction: column; align-items: center; flex: 0 0 auto !important;
        margin: 0 !important; padding: 0 !important; height: auto !important; min-height: 0 !important;
        gap: 0 !important; text-align: center;
    }}
    {instr} > div {{ display: none; }}
    {instr}::before {{
        content: "Arraste o arquivo aqui ou clique para selecionar";
        display: block; font-size: 1.05rem; color: {s['text']};
    }}
    {instr}::after {{
        content: "{_types_label()} · até {MAX_UPLOAD_MB} MB";
        display: block; margin-top: .25rem; font-size: .85rem; color: {s['muted']};
    }}
    /* Hover: realce suave. */
    {zone}:hover, {zone}:focus-within {{ border-color: {s['accent']}; background: {s['accent_bg']}; }}
    {zone}:hover::before {{ color: {s['accent']}; border-color: {s['accent']}; }}
    /* Arrastar por cima (classe posta pelo script): mudança forte e animada. */
    @keyframes mf-pulse {{
        0%, 100% {{ box-shadow: 0 0 0 0 {s['accent_strong']}; }}
        50% {{ box-shadow: 0 0 0 10px {s['accent_strong']}; }}
    }}
    {zone}.mf-dragover {{
        border-style: solid; border-color: {s['accent']}; background: {s['accent_strong']};
        transform: scale(1.01);
    }}
    {zone}.mf-dragover::before {{
        content: "download"; color: {s['card']}; background: {s['accent']}; border-color: {s['accent']};
        transform: scale(1.08); animation: mf-pulse 1.2s ease-in-out infinite;
    }}
    {zone}.mf-dragover [data-testid='stFileUploaderDropzoneInstructions']::before {{
        content: "Solte o arquivo para enviá-lo"; color: {s['accent']}; font-weight: 600;
    }}
    /* A enviar: barra de progresso com percentagem e velocidade. */
    {zone}.mf-uploading [data-testid='stFileUploaderDropzoneInstructions'] {{ visibility: hidden; }}
    {zone} .mf-progress {{
        position: absolute; left: 12%; right: 12%; bottom: 2.4rem; pointer-events: none;
        font-size: .85rem; color: {s['text']};
    }}
    {zone} .mf-progress .mf-name {{ font-weight: 600; margin-bottom: .45rem; white-space: nowrap;
        overflow: hidden; text-overflow: ellipsis; }}
    {zone} .mf-progress .mf-bar {{ height: 8px; border-radius: 99px; background: {s['track']}; overflow: hidden; }}
    {zone} .mf-progress .mf-bar span {{ display: block; height: 100%; width: 0; border-radius: 99px;
        background: {s['accent']}; transition: width .15s linear; }}
    {zone} .mf-progress .mf-meta {{ display: flex; justify-content: space-between; margin-top: .4rem;
        color: {s['muted']}; font-variant-numeric: tabular-nums; }}
    /* A lista de ficheiros do Streamlit é substituída pelos estados de sucesso/erro da página. */
    [class*='st-key-doc_upload'] [data-testid='stFileChips'] {{ display: none !important; }}
    .st-key-upload_ok {{ border: 1px solid {s['border']}; border-radius: .9rem; padding: .75rem 1rem; }}
    .st-key-upload_ok_thumb img {{ border-radius: .5rem; object-fit: cover; }}
    .st-key-upload_ok_icon span {{ font-size: 2.2rem !important; line-height: 1; }}

    /* Modo texto: campo grande e arredondado, que cresce com o texto; foco/arrastar a verde suave. */
    .st-key-doc_text [data-baseweb='textarea'] {{
        border: 1px solid {s['border']} !important; border-radius: .9rem !important;
        background: {s['zone']} !important; transition: border-color .15s ease, box-shadow .15s ease;
    }}
    .st-key-doc_text [data-baseweb='textarea']:focus-within,
    .st-key-doc_text.mf-dragover [data-baseweb='textarea'] {{
        border-color: {s['accent']} !important; box-shadow: 0 0 0 3px {s['accent_strong']};
    }}
    .st-key-doc_text textarea {{
        min-height: 240px; padding: 1rem 1.1rem !important; line-height: 1.55; resize: none;
    }}
    </style>""")


def _behaviour() -> None:
    """Script da zona de envio: realce ao arrastar e barra de progresso real do envio.

    O Streamlit envia o ficheiro por XHR (axios); o script observa os eventos de progresso
    desse pedido para mostrar percentagem e velocidade. Corre uma vez por sessão do browser.
    """
    st.html("""<script>
    (() => {
      if (window.__mfUploadUX) return;
      window.__mfUploadUX = true;
      const ZONE = "[class*='st-key-doc_upload'] [data-testid='stFileUploaderDropzone']";
      const zoneOf = (el) => el && el.closest ? el.closest(ZONE) : null;
      const clearDrag = () => document.querySelectorAll(ZONE).forEach((z) => z.classList.remove('mf-dragover'));

      document.addEventListener('dragenter', (e) => { const z = zoneOf(e.target); if (z) z.classList.add('mf-dragover'); }, true);
      document.addEventListener('dragover', (e) => { const z = zoneOf(e.target); if (z) z.classList.add('mf-dragover'); }, true);
      document.addEventListener('dragleave', (e) => {
        const z = zoneOf(e.target);
        if (z && !z.contains(e.relatedTarget)) z.classList.remove('mf-dragover');
      }, true);
      document.addEventListener('drop', clearDrag, true);
      document.addEventListener('dragend', clearDrag, true);

      const fmt = (n, d = 1) => n.toLocaleString('pt-PT', { minimumFractionDigits: d, maximumFractionDigits: d });
      // Elementos criados com createElement: o sanitizador do st.html apaga scripts com HTML em texto.
      const make = (tag, cls, parent) => { const e = document.createElement(tag); e.className = cls; parent.appendChild(e); return e; };
      function progressUI(name) {
        const z = document.querySelector(ZONE);
        if (!z) return null;
        let el = z.querySelector('.mf-progress');
        if (!el) {
          el = make('div', 'mf-progress', z);
          make('div', 'mf-name', el);
          make('span', '', make('div', 'mf-bar', el));
          const meta = make('div', 'mf-meta', el);
          make('span', 'mf-pct', meta).textContent = '0%';
          make('span', 'mf-speed', meta);
        }
        z.classList.add('mf-uploading');
        el.querySelector('.mf-name').textContent = name ? 'Enviando ' + name : 'Enviando arquivo';
        return {
          update(loaded, total, seconds) {
            const pct = total ? Math.round(loaded * 100 / total) : 0;
            el.querySelector('.mf-bar span').style.width = pct + '%';
            el.querySelector('.mf-pct').textContent = pct + '%';
            const speed = seconds > 0 ? loaded / seconds / (1024 * 1024) : 0;
            el.querySelector('.mf-speed').textContent = fmt(speed) + ' MB/s · ' + fmt(loaded / 1048576) + ' de ' + fmt(total / 1048576) + ' MB';
          },
          done() {
            el.querySelector('.mf-bar span').style.width = '100%';
            el.querySelector('.mf-pct').textContent = '100%';
            setTimeout(() => { el.remove(); z.classList.remove('mf-uploading'); }, 500);
          },
        };
      }

      // --- Modo texto -------------------------------------------------------------------
      // O Streamlit só aplica o valor do text_area ao perder o foco: depois de colar, o campo
      // perde o foco para o texto ser lido logo.
      const TEXT = "[class*='st-key-doc_text'] textarea";
      const textWrap = (el) => el && el.closest ? el.closest("[class*='st-key-doc_text']") : null;
      const setValue = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
      function commitText(ta, value) {
        ta.focus();
        setValue.call(ta, value);
        ta.dispatchEvent(new Event('input', { bubbles: true }));
        setTimeout(() => ta.blur(), 80);  // dá tempo ao React de registar o valor antes de aplicar
      }
      document.addEventListener('paste', (e) => {
        const ta = e.target.closest && e.target.closest(TEXT);
        if (ta) setTimeout(() => ta.blur(), 80);
      }, true);
      document.addEventListener('dragover', (e) => { const w = textWrap(e.target); if (w) w.classList.add('mf-dragover'); }, true);
      document.addEventListener('dragleave', (e) => {
        const w = textWrap(e.target);
        if (w && !w.contains(e.relatedTarget)) w.classList.remove('mf-dragover');
      }, true);
      document.addEventListener('drop', (e) => {
        document.querySelectorAll("[class*='st-key-doc_text']").forEach((w) => w.classList.remove('mf-dragover'));
        const ta = e.target.closest && e.target.closest(TEXT);
        const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
        if (!ta || !file) return;
        e.preventDefault();  // sem isto o browser abriria o ficheiro
        if (file.type.startsWith('text/') || /[.]txt$/i.test(file.name)) file.text().then((t) => commitText(ta, t));
      }, true);

      // --- Barra de progresso do envio de ficheiros ----------------------------------------
      const open = XMLHttpRequest.prototype.open, send = XMLHttpRequest.prototype.send;
      XMLHttpRequest.prototype.open = function (method, url) { this.__mfUrl = String(url); return open.apply(this, arguments); };
      XMLHttpRequest.prototype.send = function (body) {
        if (this.__mfUrl && this.__mfUrl.includes('upload_file') && document.querySelector(ZONE)) {
          const file = body instanceof FormData ? [...body.values()].find((v) => v instanceof File) : null;
          const ui = progressUI(file && file.name);
          if (ui) {
            const t0 = performance.now();
            this.upload.addEventListener('progress', (ev) => {
              if (ev.lengthComputable) ui.update(ev.loaded, ev.total, (performance.now() - t0) / 1000);
            });
            this.addEventListener('loadend', () => ui.done());
          }
        }
        return send.apply(this, arguments);
      };
    })();
    </script>""", unsafe_allow_javascript=True)


# --------------------------------------------------------------------------- #
# Estados e processamento
# --------------------------------------------------------------------------- #
def _process(send_fn, *args) -> None:
    """Envia para o back-end com feedback de progresso e guarda o resultado."""
    with st.status("Processando documento…", expanded=True) as status:
        st.write(":material/cloud_upload: Enviando para a API MediFlow…")
        try:
            raw = send_fn(*args)
        except APIError as err:
            status.update(label="Falha no processamento", state="error")
            show_api_error(err, "O documento não foi processado")
            return
        st.write(":material/psychology: Extração, regras e roteamento concluídos.")
        status.update(label="Documento processado", state="complete", expanded=False)

    doc = normalize_document(raw)
    st.session_state["selected_doc_id"] = doc["id"]
    st.session_state["last_result"] = raw  # útil se a API não expuser GET /documents/{id}
    st.session_state["just_processed"] = doc["id"]


def _preview(uploaded) -> None:
    """Pré-visualização nativa de imagens e PDFs."""
    if uploaded.type and uploaded.type.startswith("image/"):
        st.image(uploaded, width="stretch", alt=f"Pré-visualização de {uploaded.name}")
        return
    try:
        st.pdf(uploaded, height=420, alt=f"Pré-visualização de {uploaded.name}")
    except Exception:  # extra streamlit[pdf] não instalado
        st.caption(":material/picture_as_pdf: Pré-visualização de PDF indisponível "
                   "(instale `streamlit[pdf]`).")


def _upload_error(title: str, reason: str) -> None:
    st.error(reason, title=title, icon=":material/error:")
    st.button("Escolher outro arquivo", icon=":material/restart_alt:", on_click=_reset_upload)


def _upload_success(uploaded) -> None:
    """Ficheiro pronto: check verde, miniatura (imagem) ou ícone do tipo, nome e tamanho."""
    ext = Path(uploaded.name).suffix.lower().lstrip(".")
    with st.container(horizontal=True, vertical_alignment="center", gap="medium", key="upload_ok"):
        if uploaded.type and uploaded.type.startswith("image/"):
            with st.container(width="content", key="upload_ok_thumb"):
                st.image(uploaded, width=56, alt=f"Miniatura de {uploaded.name}")
        else:
            with st.container(width="content", key="upload_ok_icon"):
                st.markdown(f":red[{_FILE_ICONS.get(ext, ':material/description:')}]")
        with st.container(gap=None, width="stretch"):
            st.markdown(f"**{uploaded.name}**")
            st.caption(f"{ext.upper()} · {_format_mb(uploaded.size)}")
        st.badge("Pronto para processar", icon=":material/check_circle:", color="green")
        st.button("Remover", icon=":material/close:", type="tertiary", on_click=_reset_upload)


def _show_last_result() -> None:
    """Resumo do último documento processado, com atalho para o detalhe."""
    raw = st.session_state.get("last_result")
    if not raw or st.session_state.get("just_processed") is None:
        return
    doc = normalize_document(raw)
    with st.container(border=True):
        st.subheader(f"Documento {doc['id']} processado", icon=":material/check_circle:")
        badge_row(priority_badge(doc["priority"]))
        with st.container(horizontal=True):
            st.metric("Paciente", doc["extracted"]["patient_name"], icon=":material/person:", border=True)
            st.metric("Tipo", doc["extracted"]["document_type"], icon=":material/description:", border=True)
            st.metric("Destino", doc["destination"], icon=":material/alt_route:", border=True)
        if st.button("Ver análise completa", type="primary", icon=":material/arrow_forward:"):
            st.session_state["just_processed"] = None
            go_to("result", doc_id=doc["id"])


def _file_mode(backend) -> None:
    st.subheader("Documento clínico", anchor=False)
    uploaded = st.file_uploader(
        "Documento clínico",
        key=_uploader_key(),
        max_upload_size=_UPLOAD_HARD_LIMIT_MB,
        label_visibility="collapsed",
    )
    if uploaded is None:
        st.caption(":material/info: As APIs locais de demonstração e de homologação Gemini só processam as "
                   "amostras oficiais de `amostras/` (DOC-001, DOC-002 e DOC-005), com o nome original do arquivo.")
        return

    # Com um ficheiro escolhido, o cartão de sucesso/erro ocupa o lugar da zona de envio
    # ("Remover" / "Escolher outro arquivo" trazem-na de volta).
    st.html("<style>[class*='st-key-doc_upload'] { display: none !important; }</style>")
    problem = _validate(uploaded)
    if problem:
        _upload_error(*problem)
        return
    _upload_success(uploaded)
    left, right = st.columns([2, 3], gap="large")
    with left:
        if st.button("Processar documento", type="primary",
                     key="process_file", width="stretch"):
            _process(backend.upload_document, uploaded.name, uploaded.getvalue(),
                     uploaded.type or "application/octet-stream")
    with right:
        _preview(uploaded)


def _clear_text() -> None:
    st.session_state[_TEXT_KEY] = ""


def _read_text(text: str) -> dict:
    """Leitura rápida do texto colado: tamanho e tipo provável de documento (por palavras-chave)."""
    words = len(text.split())
    lower = text.lower()
    hits = {kind: sum(lower.count(k) for k in keys) for kind, keys in _DOC_HINTS}
    kind = max(hits, key=hits.get) if any(hits.values()) else None
    return {"words": words, "chars": len(text), "kind": kind,
            "too_short": words < _MIN_WORDS or len(text) < _MIN_CHARS}


def _text_mode(backend) -> None:
    st.subheader("Texto do documento", anchor=False)

    text = st.text_area(
        "Conteúdo do documento",
        key=_TEXT_KEY,
        label_visibility="collapsed",
        height="content",  # cresce com o texto (sem scroll interno); altura mínima no CSS
        placeholder="Cole aqui o texto completo da receita, pedido de exames ou relatório...",
    )

    reading = None
    if text.strip():
        cached = st.session_state.get(_TEXT_READ)
        if cached and cached[0] == text:
            reading = cached[1]
        else:
            # Leitura rápida a cada texto novo, com um indicador discreto.
            with st.spinner("Lendo o texto…"):
                time.sleep(0.4)
                reading = _read_text(text)
            st.session_state[_TEXT_READ] = (text, reading)

        if reading["too_short"]:
            st.error("O texto colado parece muito curto. Certifique-se de colar o conteúdo completo "
                     "do documento.", icon=":material/error:")

    # Rodapé: estado da leitura à esquerda, ação principal à direita.
    valid = reading is not None and not reading["too_short"]
    with st.container(horizontal=True, vertical_alignment="center"):
        if valid:
            with st.container(horizontal=True, wrap=False, vertical_alignment="center", gap="small",
                              width="content"):
                st.badge("Texto lido", icon=":material/check_circle:", color="green")
                details = f"{reading['words']} palavras · {reading['chars']} caracteres"
                if reading["kind"]:
                    details += f" · parece {reading['kind'].lower()}"
                st.caption(details, width="content")
        st.space("stretch")  # empurra as ações para a direita do cartão, haja ou não estado
        st.button(":material/delete:", key="text_clear", type="tertiary", help="Limpar o texto",
                  disabled=not text, on_click=_clear_text)
        clicked = st.button("Processar documento", type="primary",
                            disabled=not valid, key="process_text")
    if clicked:
        _process(backend.submit_text, text.strip())


def render() -> None:
    page_header("Enviar documento", "Envie uma receita, pedido de exame ou relatório para triagem automática.",
                icon=":material/upload_file:")
    backend = get_backend()

    mode = st.segmented_control("Tipo de entrada", list(_MODES), format_func=_MODES.get,
                                default="file", required=True, label_visibility="collapsed", key="upload_mode")

    _styles()
    with st.container(border=True, key="upload_card"):
        if mode == "file":
            _file_mode(backend)
        else:
            _text_mode(backend)

    _show_last_result()
    _behaviour()  # no fim da página: o elemento do script não empurra o resto do conteúdo
