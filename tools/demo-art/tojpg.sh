#!/usr/bin/env bash
# PNG -> JPEG a bongeszo canvasaval: a kornyezet ffmpeg-jeben nincs PNG-dekoder
# es nincs JPEG-enkoder, ImageMagick es PIL sincs. A Chromium mindkettot tudja.
set -euo pipefail
src="$1"; dst="$2"; q="${3:-0.86}"; w="${4:-0}"
dir="$(cd "$(dirname "$src")" && pwd)"
page="$dir/.conv-$(basename "$dst").html"
cat > "$page" <<HTML
<!doctype html><meta charset="utf-8"><body><div id="o"></div><script>
const img = new Image();
img.onload = () => {
  const scale = ${w} > 0 ? ${w} / img.width : 1;
  const c = document.createElement('canvas');
  c.width = Math.round(img.width * scale); c.height = Math.round(img.height * scale);
  const x = c.getContext('2d');
  x.imageSmoothingQuality = 'high';
  x.drawImage(img, 0, 0, c.width, c.height);
  document.getElementById('o').textContent = c.toDataURL('image/jpeg', ${q});
};
img.onerror = () => { document.getElementById('o').textContent = 'ERROR'; };
img.src = 'file://$src';
</script></body>
HTML
/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell \
  --no-sandbox --disable-gpu --allow-file-access-from-files --virtual-time-budget=15000 --dump-dom "file://$page" 2>/dev/null \
  | python3 -c "
import sys, base64, re, pathlib
html = sys.stdin.read()
m = re.search(r'data:image/jpeg;base64,([A-Za-z0-9+/=]+)', html)
if not m:
    sys.exit('nem sikerult a konvertalas (a canvas nem adott adatot)')
pathlib.Path('$dst').write_bytes(base64.b64decode(m.group(1)))
print('ok')
"
rm -f "$page"
