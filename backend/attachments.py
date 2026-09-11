"""Szöveg kinyerése a levélmellékletekből.

Miért kell:

Egy levél, aminek a törzse üres és a lényeg egy csatolt dokumentumban van,
teljesen valós eset — a demó során pont ez fordult elő: 2 bájt szöveg, 27 bájt
HTML, és egy 3 MB-os Word-melléklet. Az agent „üres levélnek" látta, és
ennek megfelelően semmit nem tudott mondani róla.

Amit szándékosan NEM csinál:

  * nem tölt le mindent — csak akkor nyúl a melléklethez, ha a levéltörzs
    önmagában kevés, mert egy csatolmány letöltése idő és sávszélesség;
  * nem OCR-ez — egy szkennelt PDF-ből nem lesz szöveg, és ezt meg is mondja
    ahelyett, hogy üres eredményt adna vissza;
  * nem futtat semmit és nem old fel külső hivatkozást a dokumentumokból.

A védelem nem opcionális: egy csatolmány idegen adat. Van méretkorlát a
letöltésre, van külön korlát a kicsomagolt méretre (egy néhány kilobájtos
Office-fájl gigabájtokra tud kitömöríteni), és van korlát a modellnek átadott
szövegen.
"""
import io
import logging
import re
import xml.etree.ElementTree as ET
import zipfile

logger = logging.getLogger(__name__)

# Amit letöltünk. Egy tipikus ajánlat vagy számla ezen belül van; ami nem, azt
# úgysem a demó fogja feldolgozni.
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
# Kicsomagolás után. Egy 100 kB-os docx, ami 500 MB-ra tömörül ki, nem hiba,
# hanem támadás — ezért a kicsomagolt méretet külön kell nézni.
MAX_UNPACKED_BYTES = 25 * 1024 * 1024
# Mellékletenként és levelenként a modellnek átadott szöveg.
MAX_CHARS_PER_ATTACHMENT = 4000
MAX_ATTACHMENTS_PER_EMAIL = 2

# Office-formátumok: mind ZIP + XML, tehát stdlib-bel olvashatók.
_WORD = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_PPT = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_PDF = "application/pdf"

SUPPORTED = {_WORD, _EXCEL, _PPT, _PDF, "text/plain", "text/csv", "text/markdown"}

_EXT_TO_MIME = {
    ".docx": _WORD, ".xlsx": _EXCEL, ".pptx": _PPT, ".pdf": _PDF,
    ".txt": "text/plain", ".csv": "text/csv", ".md": "text/markdown",
}


# Amit a küldő akkor ad, ha nem tudja megmondani, mi az. Csak ezeknél nézünk
# kiterjesztést — egy határozott, de nem támogatott MIME (mondjuk image/png egy
# .docx néven) inkább félrevezetés vagy hiba, mint fogódzó.
_VAGUE_MIMES = {"", "application/octet-stream", "binary/octet-stream", "application/unknown"}


def kind_of(filename: str, mime: str) -> str:
    """A tényleges típus.

    A Gmail néha application/octet-stream-et ad, és ilyenkor a kiterjesztés az
    egyetlen támpont. Ha viszont a MIME határozott — csak épp nem olyasmi, amit
    olvasni tudunk —, azt fogadjuk el, és nem írjuk felül a fájlnév alapján.
    """
    mime = (mime or "").split(";")[0].strip().lower()
    if mime in SUPPORTED:
        return mime
    if mime not in _VAGUE_MIMES:
        return ""
    ext = re.search(r"(\.[A-Za-z0-9]+)$", filename or "")
    if ext:
        return _EXT_TO_MIME.get(ext.group(1).lower(), "")
    return ""


def _zip_entries_text(data: bytes, wanted) -> str:
    """XML szöveg egy Office-csomagból, kicsomagolási korláttal."""
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        total = sum(i.file_size for i in z.infolist())
        if total > MAX_UNPACKED_BYTES:
            raise ValueError(f"unpacked size {total} over limit")
        names = [n for n in z.namelist() if wanted(n)]
        for name in sorted(names):
            try:
                out.append(_xml_text(z.read(name)))
            except Exception as e:  # noqa - egy rossz rész ne vigye el a többit
                logger.debug("skipping %s: %s", name, type(e).__name__)
    return "\n".join(t for t in out if t)


def _xml_text(raw: bytes) -> str:
    """Minden szöveg egy XML-ből, a címkéktől függetlenül.

    A bekezdés- és sorvégeket megtartjuk, különben a teljes dokumentum egyetlen
    összefolyt mondattá válik, és a modell sem tud mit kezdeni vele.
    """
    root = ET.fromstring(raw)
    parts = []
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag in ("p", "br", "tr", "sheetData", "row"):
            parts.append("\n")
        if el.text and el.text.strip():
            parts.append(el.text)
    return re.sub(r"\n{3,}", "\n\n", "".join(parts)).strip()


def _docx(data: bytes) -> str:
    return _zip_entries_text(data, lambda n: n == "word/document.xml")


def _pptx(data: bytes) -> str:
    return _zip_entries_text(data, lambda n: re.fullmatch(r"ppt/slides/slide\d+\.xml", n))


def _xlsx(data: bytes) -> str:
    # A cellák többsége a sharedStrings-ben van, nem a munkalapon.
    return _zip_entries_text(
        data, lambda n: n == "xl/sharedStrings.xml" or re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)
    )


def _pdf(data: bytes) -> str:
    from pypdf import PdfReader  # lusta import: csak PDF-nél kell

    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages[:20]:  # egy 200 oldalas melléklet nem demó-anyag
        pages.append(page.extract_text() or "")
        if sum(len(p) for p in pages) > MAX_CHARS_PER_ATTACHMENT * 2:
            break
    return "\n".join(pages).strip()


_READERS = {
    _WORD: _docx, _EXCEL: _xlsx, _PPT: _pptx, _PDF: _pdf,
    "text/plain": lambda d: d.decode("utf-8", errors="replace"),
    "text/csv": lambda d: d.decode("utf-8", errors="replace"),
    "text/markdown": lambda d: d.decode("utf-8", errors="replace"),
}


def extract_text(filename: str, mime: str, data: bytes) -> str:
    """A melléklet szövege, vagy üres string, ha nem megy.

    Soha nem dob kivételt: egy hibás csatolmány nem indokolja, hogy az egész
    levél kiessen a futásból.
    """
    kind = kind_of(filename, mime)
    reader = _READERS.get(kind)
    if not reader or not data:
        return ""
    try:
        text = reader(data)
    except Exception as e:  # noqa - sérült, jelszavas vagy ismeretlen belső szerkezet
        logger.info("attachment unreadable (%s): %s", filename, type(e).__name__)
        return ""
    text = re.sub(r"[ \t]+", " ", text or "").strip()
    if len(text) > MAX_CHARS_PER_ATTACHMENT:
        text = text[:MAX_CHARS_PER_ATTACHMENT] + "\n[…a melléklet további része levágva]"
    return text


def list_candidates(payload: dict) -> list:
    """A levélben lévő, feldolgozható méretű és típusú mellékletek.

    A visszaadott elemekben ott az attachmentId, amivel a Gmail API-tól le lehet
    kérni a tartalmat — a letöltést szándékosan nem ez a modul végzi, hogy a
    kinyerés hálózat nélkül tesztelhető maradjon.
    """
    found = []

    def walk(part):
        body = part.get("body") or {}
        filename = part.get("filename") or ""
        if filename and body.get("attachmentId"):
            size = body.get("size") or 0
            kind = kind_of(filename, part.get("mimeType", ""))
            if kind and size <= MAX_ATTACHMENT_BYTES:
                found.append({
                    "filename": filename,
                    "mime": kind,
                    "size": size,
                    "attachment_id": body["attachmentId"],
                })
        for sub in part.get("parts") or []:
            walk(sub)

    walk(payload or {})
    # A kisebbek előre: két kis dokumentum többet mond, mint egy nagy fele.
    found.sort(key=lambda a: a["size"])
    return found[:MAX_ATTACHMENTS_PER_EMAIL]
