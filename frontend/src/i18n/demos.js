// A demóoldalak közös szövegei (sáv, figyelmeztetés, űrlapcímkék, referenciakártyák).
// Az oldalak saját tartalma: src/demos/content/*.js (hu, en, de; a többi nyelv angolul).
const demos = {
  "hu": {
    "back": "← Vissza az AXIMBRA-hoz",
    "noticeTag": "DEMÓ",
    "noticeText": "Ez egy bemutató oldal, nem valós vállalkozás. A márkát, a címeket, az árakat és a munkatársakat mi találtuk ki; a megadott adatokat nem küldjük el és nem tároljuk. Készítette: AXIMBRA.",
    "labels": {
      "address": "Cím",
      "phone": "Telefon",
      "email": "E-mail",
      "hours": "Nyitvatartás",
      "send": "Küldés",
      "name": "Név",
      "message": "Miben segíthetünk?",
      "sent": "Köszönjük! Hamarosan jelentkezünk.",
      "consent": "Elfogadom, hogy ez egy bemutató űrlap: a beírt adatok nem kerülnek elküldésre és tárolásra.",
      "sentDemo": "Ez egy bemutató — nem küldtünk el semmit, és a beírt adatokat nem tároltuk. Egy valódi oldalon itt futna az AXIMBRA ajánlatkérő agentje.",
      "enlarge": "kép nagyban",
      "close": "Bezárás",
      "demo": "demó"
    },
    "refs": {
      "tag": "Referenciák",
      "heading": "Négy demó, négy világ",
      "sub": "Mindegyik oldal kitalált márkának készült, saját vizuális nyelvvel és saját interaktív elemmel — és mindegyikben ott dolgozik egy AXIMBRA-agent.",
      "view": "Megnézem →",
      "copy": "Link másolása",
      "copied": "Kimásolva!",
      "cards": [
        {
          "tag": "Fogászat",
          "title": "LUMEN · fogászat",
          "desc": "Animált fog, előtte–utána csúszka, árkalkulátor és éjjel is válaszoló AI-recepció."
        },
        {
          "tag": "Étterem",
          "title": "PARÁZS · tűzkonyha",
          "desc": "Felszálló parázs, kóstolómenü fogásról fogásra, élő asztalfoglalás."
        },
        {
          "tag": "Ügyvédi iroda",
          "title": "VERITAS · ügyvédi iroda",
          "desc": "Billenő mérleg és 60 másodperces ügyfelmérő, ami a sürgős ügyeket azonnal jelzi."
        },
        {
          "tag": "Webshop",
          "title": "ŐRLŐ · kávépörkölő",
          "desc": "Pörkölési ízkereső, kosár, és „Hol a csomagom?” ügyfélszolgálati agenttel."
        }
      ]
    }
  },
  "en": {
    "back": "← Back to AXIMBRA",
    "noticeTag": "DEMO",
    "noticeText": "This is a showcase page, not a real business. The brand, addresses, prices and staff are invented; anything you type here is neither sent nor stored. Built by AXIMBRA.",
    "labels": {
      "address": "Address",
      "phone": "Phone",
      "email": "Email",
      "hours": "Opening hours",
      "send": "Send",
      "name": "Name",
      "message": "How can we help?",
      "sent": "Thank you! We'll be in touch shortly.",
      "consent": "I understand this is a demo form: nothing I type is sent or stored.",
      "sentDemo": "This is a demo — nothing was sent and nothing was stored. On a real site, AXIMBRA's intake agent would run here.",
      "enlarge": "enlarged",
      "close": "Close",
      "demo": "demo"
    },
    "refs": {
      "tag": "References",
      "heading": "Four demos, four worlds",
      "sub": "Each site is built for an invented brand, with its own visual language and its own interactive piece — and an AXIMBRA agent at work in every one.",
      "view": "View →",
      "copy": "Copy link",
      "copied": "Copied!",
      "cards": [
        {
          "tag": "Dental clinic",
          "title": "LUMEN · dental",
          "desc": "Animated tooth, before/after slider, price estimator and an AI reception that answers at night."
        },
        {
          "tag": "Restaurant",
          "title": "PARÁZS · fire kitchen",
          "desc": "Rising embers, a course-by-course tasting menu, live table booking."
        },
        {
          "tag": "Law firm",
          "title": "VERITAS · law firm",
          "desc": "Tipping scales and a 60-second case check that flags urgent matters at once."
        },
        {
          "tag": "Web shop",
          "title": "ŐRLŐ · coffee roasters",
          "desc": "Roast-level flavour finder, cart, and “Where's my parcel?” with a support agent."
        }
      ]
    }
  },
  "de": {
    "back": "← Zurück zu AXIMBRA",
    "noticeTag": "DEMO",
    "noticeText": "Dies ist eine Vorführseite, kein echtes Unternehmen. Marke, Adressen, Preise und Mitarbeitende sind erfunden; was Sie hier eingeben, wird weder gesendet noch gespeichert. Erstellt von AXIMBRA.",
    "labels": {
      "address": "Adresse",
      "phone": "Telefon",
      "email": "E-Mail",
      "hours": "Öffnungszeiten",
      "send": "Senden",
      "name": "Name",
      "message": "Wie können wir helfen?",
      "sent": "Vielen Dank! Wir melden uns in Kürze.",
      "consent": "Mir ist klar, dass dies ein Demo-Formular ist: Nichts von dem, was ich eingebe, wird gesendet oder gespeichert.",
      "sentDemo": "Dies ist eine Demo — nichts wurde gesendet und nichts gespeichert. Auf einer echten Website würde hier der Anfrage-Agent von AXIMBRA laufen.",
      "enlarge": "vergrößert",
      "close": "Schließen",
      "demo": "Demo"
    },
    "refs": {
      "tag": "Referenzen",
      "heading": "Vier Demos, vier Welten",
      "sub": "Jede Seite ist für eine erfundene Marke gebaut, mit eigener Bildsprache und eigenem interaktiven Element — und überall arbeitet ein AXIMBRA-Agent.",
      "view": "Ansehen →",
      "copy": "Link kopieren",
      "copied": "Kopiert!",
      "cards": [
        {
          "tag": "Zahnarztpraxis",
          "title": "LUMEN · Zahnarztpraxis",
          "desc": "Animierter Zahn, Vorher-nachher-Regler, Kostenrechner und eine KI-Rezeption, die auch nachts antwortet."
        },
        {
          "tag": "Restaurant",
          "title": "PARÁZS · Feuerküche",
          "desc": "Aufsteigende Glut, Degustationsmenü Gang für Gang, Live-Tischreservierung."
        },
        {
          "tag": "Kanzlei",
          "title": "VERITAS · Rechtsanwälte",
          "desc": "Eine Waage, die sich neigt, und ein 60-Sekunden-Fallcheck, der dringende Fälle sofort meldet."
        },
        {
          "tag": "Webshop",
          "title": "ŐRLŐ · Kaffeerösterei",
          "desc": "Geschmacksfinder nach Röstgrad, Warenkorb und „Wo ist mein Paket?“ mit Service-Agent."
        }
      ]
    }
  },
  "zh": {
    "back": "← 返回 AXIMBRA",
    "noticeTag": "演示",
    "noticeText": "这是一个展示页面，不是真实的企业。品牌、地址、价格和员工均为虚构；您在这里输入的任何内容都不会被发送或存储。由 AXIMBRA 制作。",
    "labels": {
      "address": "地址",
      "phone": "电话",
      "email": "邮箱",
      "hours": "营业时间",
      "send": "发送",
      "name": "姓名",
      "message": "我们能帮您做什么？",
      "sent": "谢谢！我们会尽快与您联系。",
      "consent": "我知道这是一个演示表单：我输入的内容不会被发送或存储。",
      "sentDemo": "这是一个演示——没有发送任何内容，也没有存储任何内容。在真实网站上，这里会运行 AXIMBRA 的咨询接收代理。",
      "enlarge": "放大",
      "close": "关闭",
      "demo": "演示"
    },
    "refs": {
      "tag": "参考网站",
      "view": "查看 →",
      "copy": "复制链接",
      "copied": "已复制！"
    }
  }
};

export default demos;
