#!/usr/bin/env bash
###############################################################################
# Diagram-Studio LXC Installer — Community-Script-Stil
#
# Erstellt auf dem Proxmox-Host einen LXC mit der Diagram-Studio Web-UI:
#   - Diagramme per KI oder Schnell-Entwurf erzeugen (diagram-design Skill)
#   - Vorschau + direkter Download-Button (HTML)
#   - Einstellungsseite für OmniRoute- und OpenRouter-API (Basis-URL, Key, Modell)
#
# Verwendung auf dem PROXMOX-HOST als root:
#   bash -c "$(curl -fsSL http://192.168.178.51:8090/diagram-studio-install.sh)"
#
# Optionale Umgebungsvariablen:
#   VMID=200 HN=diagram-studio CORES=2 MEMORY=2048 DISK=8 BRIDGE=vmbr0
#   PASSWORD=geheim PORT=8123 ARTIFACT_BASE=http://192.168.178.51:8090
#   STORAGE=local-lvm TEMPLATE="local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst"
#   REUSE=1  (bestehenden Container $VMID weiterinstallieren statt neu erstellen)
###############################################################################
set -euo pipefail

APP="diagram-studio"
PORT="${PORT:-8123}"
HN="${HN:-diagram-studio}"
CORES="${CORES:-2}"
MEMORY="${MEMORY:-2048}"
DISK="${DISK:-8}"
BRIDGE="${BRIDGE:-vmbr0}"
ARTIFACT_BASE="${ARTIFACT_BASE:-http://192.168.178.51:8090}"
TARBALL_URL="${TARBALL_URL:-$ARTIFACT_BASE/diagram-studio.tar.gz}"

msg()  { echo -e "\033[1;32m[diagram-studio]\033[0m $*"; }
warn() { echo -e "\033[1;33m[diagram-studio]\033[0m $*" >&2; }
fail() { echo -e "\033[1;31m[diagram-studio]\033[0m $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "Bitte als root auf dem Proxmox-Host ausführen."
command -v pct >/dev/null || fail "pct nicht gefunden — das Skript muss auf dem Proxmox-Host laufen."
command -v pvesh >/dev/null || fail "pvesh nicht gefunden."

NODE="$(hostname)"
msg "Node: $NODE"

# --- VMID ---
if [ -z "${VMID:-}" ]; then
  VMID="$(pvesh get /cluster/nextid)"
fi
msg "VMID: $VMID"
if pct status "$VMID" >/dev/null 2>&1; then
  if [ "${REUSE:-0}" = "1" ]; then
    warn "VMID $VMID existiert bereits — REUSE=1, überspringe Erstellung."
    pct start "$VMID" 2>/dev/null || true
  else
    fail "VMID $VMID ist bereits belegt (pct destroy $VMID für neu, oder REUSE=1 VMID=$VMID … zum Weiterinstallieren)."
  fi
else

# --- Storage (rootdir-fähig, bevorzugt local-lvm, dann local) ---
if [ -z "${STORAGE:-}" ]; then
  STORAGE="$(pvesh get /storage --output-format json 2>/dev/null | python3 -c "
import json,sys
try: stores=json.load(sys.stdin)
except Exception: stores=[]
def ok(s): return s.get('enabled',1)==1 and 'rootdir' in str(s.get('content',''))
names=[s['storage'] for s in stores if isinstance(s,dict) and ok(s) and s.get('storage')]
for pref in ('local-lvm','local'):
    if pref in names: print(pref); break
else: print(names[0] if names else '')
")"
fi
[ -n "${STORAGE:-}" ] || fail "Kein rootdir-fähiges Storage gefunden."
msg "Storage: $STORAGE"

# --- Template (Debian 12 Standard, ggf. herunterladen) ---
if [ -z "${TEMPLATE:-}" ]; then
  TPL_STORE="local"
  HAVE="$(pveam list "$TPL_STORE" 2>/dev/null | grep -o 'debian-12-standard_[^ ]*amd64.tar.zst' | sort | tail -n 1 || true)"
  if [ -z "$HAVE" ]; then
    msg "Lade Debian-12-Template (kann dauern) …"
    CAND="$(pveam available --section system 2>/dev/null | grep -o 'debian-12-standard_[^ ]*amd64.tar.zst' | sort | tail -n 1 || true)"
    [ -n "$CAND" ] || fail "Kein debian-12-standard Template im Angebot gefunden."
    pveam download "$TPL_STORE" "$CAND" >/dev/null || fail "Template-Download fehlgeschlagen."
    HAVE="$CAND"
  fi
  TEMPLATE="$TPL_STORE:vztmpl/$HAVE"
fi
msg "Template: $TEMPLATE"

# --- Passwort ---
if [ -z "${PASSWORD:-}" ]; then
  PASSWORD="$(openssl rand -base64 12 | tr -dc 'A-Za-z0-9' | head -c 14)"
  GEN_PW=1
else
  GEN_PW=0
fi

# --- Container erstellen & starten ---
msg "Erstelle LXC $VMID ($HN, ${CORES}c/${MEMORY}MB/${DISK}G) …"
pct create "$VMID" "$TEMPLATE" \
  --hostname "$HN" --cores "$CORES" --memory "$MEMORY" --swap 512 \
  --rootfs "$STORAGE:$DISK" \
  --net0 "name=eth0,bridge=$BRIDGE,ip=dhcp" \
  --unprivileged 1 --features nesting=1 --onboot 1 \
  --password "$PASSWORD" --start 1
fi

msg "Warte auf Netzwerk im Container …"
IP=""
for i in $(seq 1 40); do
  IP="$(pct exec "$VMID" -- hostname -I 2>/dev/null | awk '{print $1}' || true)"
  [ -n "$IP" ] && break
  sleep 3
done
[ -n "$IP" ] || fail "Container hat keine IP bekommen (DHCP prüfen)."

# --- App installieren ---
msg "Installiere Diagram-Studio …"
pct exec "$VMID" -- bash -c "apt-get update -qq && apt-get install -y -qq python3 curl >/dev/null && mkdir -p /opt/diagram-studio/generated"
curl -fsSL "$TARBALL_URL" -o /tmp/diagram-studio.tar.gz || fail "Tarball-Download fehlgeschlagen: $TARBALL_URL"
pct push "$VMID" /tmp/diagram-studio.tar.gz /tmp/diagram-studio.tar.gz
pct exec "$VMID" -- bash -c "tar xzf /tmp/diagram-studio.tar.gz --strip-components=1 -C /opt/diagram-studio && cp /opt/diagram-studio/diagram-studio.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now diagram-studio"
rm -f /tmp/diagram-studio.tar.gz

sleep 2
pct exec "$VMID" -- bash -c "curl -fsS -o /dev/null http://127.0.0.1:$PORT/" || fail "Health-Check der App fehlgeschlagen."

echo
msg "FERTIG ✅  http://$IP:$PORT"
[ "${GEN_PW:-0}" -eq 1 ] && msg "LXC-root-Passwort (einmalig notieren): $PASSWORD"
msg "KI einrichten: im Browser oben auf 'Einstellungen (KI)' → Anbieter wählen,"
msg "     OmniRoute-Key oder OpenRouter-Key eintragen, Modell setzen, speichern."
msg "Update der App: Tarball erneut ausrollen mit"
msg "     curl -fsSL $TARBALL_URL -o /tmp/ds.tgz && pct push $VMID /tmp/ds.tgz /tmp/ds.tgz && pct exec $VMID -- bash -c 'tar xzf /tmp/ds.tgz --strip-components=1 -C /opt/diagram-studio && systemctl restart diagram-studio'"
