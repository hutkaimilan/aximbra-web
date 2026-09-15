"""Minimális DNS-kliens nyers UDP-n. Nincs a gépen dig/host/nslookup/dnspython,
DoH is blokkolt — enélkül a TXT- és CNAME-rekordokról csak tippelni lehetne."""
import socket, struct, sys, random

TYPES = {"A": 1, "NS": 2, "CNAME": 5, "SOA": 6, "TXT": 16, "AAAA": 28, "CAA": 257}
RTYPE = {v: k for k, v in TYPES.items()}


def servers():
    out = []
    try:
        for line in open("/etc/resolv.conf"):
            if line.startswith("nameserver"):
                out.append(line.split()[1])
    except OSError:
        pass
    return out or ["8.8.8.8", "1.1.1.1"]


def encode(name):
    b = b""
    for part in name.rstrip(".").split("."):
        b += bytes([len(part)]) + part.encode()
    return b + b"\x00"


def read_name(buf, i):
    parts = []
    jumped = False
    end = i
    while True:
        ln = buf[i]
        if ln & 0xC0 == 0xC0:
            ptr = struct.unpack("!H", buf[i:i + 2])[0] & 0x3FFF
            if not jumped:
                end = i + 2
            jumped = True
            i = ptr
            continue
        i += 1
        if ln == 0:
            if not jumped:
                end = i
            break
        parts.append(buf[i:i + ln].decode("latin1"))
        i += ln
    return ".".join(parts), end


def query(name, rtype, server, timeout=5):
    qid = random.randint(0, 65535)
    pkt = struct.pack("!HHHHHH", qid, 0x0100, 1, 0, 0, 0)
    pkt += encode(name) + struct.pack("!HH", TYPES[rtype], 1)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(pkt, (server, 53))
        buf, _ = s.recvfrom(4096)
    finally:
        s.close()
    _, flags, qd, an, ns, ar = struct.unpack("!HHHHHH", buf[:12])
    rcode = flags & 0xF
    i = 12
    for _ in range(qd):
        _, i = read_name(buf, i)
        i += 4
    out = []
    for _ in range(an + ns):
        nm, i = read_name(buf, i)
        t, _cls, _ttl, dl = struct.unpack("!HHIH", buf[i:i + 10])
        i += 10
        data = buf[i:i + dl]
        if t == 5 or t == 2:
            val, _ = read_name(buf, i)
        elif t == 16:
            val = ""
            j = 0
            while j < len(data):
                ln = data[j]
                val += data[j + 1:j + 1 + ln].decode("latin1")
                j += 1 + ln
        elif t == 1:
            val = socket.inet_ntoa(data)
        elif t == 257:
            val = f"flags={data[0]} {data[2:2+data[1]].decode('latin1')} {data[2+data[1]:].decode('latin1')}"
        elif t == 6:
            val = "SOA"
        else:
            val = data.hex()
        out.append((nm, RTYPE.get(t, str(t)), val))
        i += dl
    return rcode, out


srv = servers()[0]

DEFAULT = [
    ("aximbra.hu", "NS"), ("aximbra.hu", "CNAME"), ("aximbra.hu", "A"),
    ("aximbra.hu", "TXT"), ("aximbra.hu", "CAA"),
    ("www.aximbra.hu", "CNAME"), ("www.aximbra.hu", "A"), ("www.aximbra.hu", "TXT"),
]

if len(sys.argv) > 1:
    name = sys.argv[1]
    kinds = sys.argv[2:] or ["NS", "CNAME", "A", "TXT", "CAA"]
    plan = [(name, k.upper()) for k in kinds]
else:
    plan = DEFAULT

print(f"# feloldó: {srv}\n")
for name, rt in plan:
    try:
        rcode, ans = query(name, rt, srv)
    except Exception as e:
        print(f"{name:34} {rt:6} HIBA: {e}")
        continue
    status = {0: "OK", 3: "NXDOMAIN"}.get(rcode, f"rcode={rcode}")
    rows = [f"{t}={v}" for n, t, v in ans if t == rt or t == "CNAME"]
    print(f"{name:34} {rt:6} {status:9} {'  '.join(rows) if rows else '— nincs ilyen rekord'}")
