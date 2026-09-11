"""A melléklet-olvasás tesztjei.

Hálózat nélkül: a kinyerés szándékosan külön modul, hogy valódi fájlokon
lehessen ellenőrizni, Gmail-hívás nélkül.
"""
import io
import os
import sys
import zipfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

import attachments as A

WORD = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPT = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _zip(files, compress=zipfile.ZIP_DEFLATED):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compress) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def _docx(paragraphs):
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = ('<?xml version="1.0"?><w:document '
           'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f"<w:body>{body}</w:body></w:document>")
    return _zip({"[Content_Types].xml": "<Types/>", "word/document.xml": xml})


def test_reads_a_word_document():
    """A konkrét eset, ami a demóban előjött: üres törzs, a lényeg a .docx-ben."""
    data = _docx(["Tisztelt Címzett!", "Az ajánlatunk 250 000 Ft + áfa.", "Üdvözlettel"])
    text = A.extract_text("ajanlat.docx", WORD, data)
    assert "250 000 Ft" in text
    assert "Tisztelt Címzett!" in text
    # a bekezdések nem folynak egybe, különben olvashatatlan a modellnek is
    assert "\n" in text


def test_reads_a_spreadsheet_including_shared_strings():
    """A cellák többsége a sharedStrings-ben van, nem a munkalapon — aki csak a
    sheet1.xml-t nézi, üres táblázatot lát."""
    shared = ('<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/'
              'spreadsheetml/2006/main"><si><t>Havi díj</t></si><si><t>48000</t></si></sst>')
    sheet = ('<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/'
             'spreadsheetml/2006/main"><sheetData><row><c t="s"><v>0</v></c></row></sheetData></worksheet>')
    data = _zip({"xl/sharedStrings.xml": shared, "xl/worksheets/sheet1.xml": sheet})
    text = A.extract_text("dijak.xlsx", EXCEL, data)
    assert "Havi díj" in text and "48000" in text


def test_reads_a_presentation():
    slide = ('<?xml version="1.0"?><p:sld xmlns:p="http://schemas.openxmlformats.org/'
             'presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/'
             'drawingml/2006/main"><a:t>Bevezető ajánlat</a:t></p:sld>')
    data = _zip({"ppt/slides/slide1.xml": slide})
    assert "Bevezető ajánlat" in A.extract_text("deck.pptx", PPT, data)


def test_reads_plain_text_and_csv():
    assert "sor1" in A.extract_text("a.txt", "text/plain", b"sor1\nsor2")
    assert "nev;ar" in A.extract_text("a.csv", "text/csv", b"nev;ar\nx;100")


def test_falls_back_to_the_extension_when_the_mime_is_useless():
    """A Gmail néha application/octet-stream-et ad; ilyenkor a kiterjesztés az
    egyetlen támpont."""
    data = _docx(["Szerződéstervezet"])
    assert "Szerződéstervezet" in A.extract_text("szerzodes.docx", "application/octet-stream", data)
    # de ha a MIME értelmes, azt hisszük el, nem a kiterjesztést
    assert A.kind_of("kep.docx", "image/png") == ""


def test_unsupported_types_are_skipped_not_guessed():
    for name, mime in [("kep.png", "image/png"), ("a.zip", "application/zip"),
                       ("v.mp4", "video/mp4"), ("a.exe", "application/octet-stream")]:
        assert A.extract_text(name, mime, b"barmi") == "", name


def test_a_corrupt_file_yields_nothing_and_does_not_raise():
    """Egy sérült melléklet nem indokolja, hogy a levél kiessen a futásból."""
    assert A.extract_text("a.docx", WORD, b"nem is zip") == ""
    assert A.extract_text("a.pdf", "application/pdf", b"%PDF-hamis") == ""
    assert A.extract_text("a.xlsx", EXCEL, _zip({"semmi.xml": "<a/>"})) == ""


def test_a_zip_bomb_is_refused():
    """Egy néhány kilobájtos Office-fájl gigabájtokra tud kitömöríteni. A
    letöltési méret korlátja ezt nem fogja meg — a kicsomagoltat kell nézni."""
    huge = "A" * (A.MAX_UNPACKED_BYTES + 1024)
    bomb = _zip({"word/document.xml": huge})
    assert len(bomb) < 200_000, "a fixture maga kicsi, pont ez a lényeg"
    assert A.extract_text("bomba.docx", WORD, bomb) == ""


def test_long_text_is_truncated_before_it_reaches_the_model():
    data = _docx(["sor " * 4000])
    text = A.extract_text("hosszu.docx", WORD, data)
    assert len(text) <= A.MAX_CHARS_PER_ATTACHMENT + 60
    assert "levágva" in text


def _payload(parts):
    return {"mimeType": "multipart/mixed", "body": {}, "parts": parts}


def _att(filename, mime, size, aid="a1"):
    return {"filename": filename, "mimeType": mime,
            "body": {"attachmentId": aid, "size": size}}


def test_candidates_skip_oversized_and_unsupported():
    payload = _payload([
        {"mimeType": "text/plain", "body": {"data": "eA=="}},
        _att("ajanlat.docx", WORD, 50_000, "ok"),
        _att("video.mp4", "video/mp4", 1000, "nem"),
        _att("hatalmas.pdf", "application/pdf", A.MAX_ATTACHMENT_BYTES + 1, "nagy"),
    ])
    ids = [a["attachment_id"] for a in A.list_candidates(payload)]
    assert ids == ["ok"]


def test_candidates_are_capped_and_smallest_first():
    """Két kis dokumentum többet mond, mint egy nagy fele."""
    payload = _payload([
        _att("nagy.docx", WORD, 900_000, "nagy"),
        _att("kicsi.docx", WORD, 1_000, "kicsi"),
        _att("kozepes.docx", WORD, 50_000, "kozepes"),
        _att("negyedik.docx", WORD, 60_000, "negyedik"),
    ])
    got = A.list_candidates(payload)
    assert len(got) == A.MAX_ATTACHMENTS_PER_EMAIL
    assert [a["attachment_id"] for a in got] == ["kicsi", "kozepes"]


def test_inline_parts_without_an_attachment_id_are_not_candidates():
    """A levéltörzs maga is 'part', de nincs attachmentId-ja — nem melléklet."""
    payload = _payload([{"mimeType": "text/plain", "filename": "", "body": {"data": "eA=="}}])
    assert A.list_candidates(payload) == []
