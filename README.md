# Diagram-Studio

Web-UI zum Erstellen von Diagrammen nach dem **diagram-design** Skill-System
(40 Diagrammtypen, editorial Design, self-contained HTML + SVG).

- **Erstellen-Tab:** Beschreibung eingeben, Typ wählen (Architektur, Flowchart, Sequenz, …),
  per KI erzeugen oder Schnell-Entwurf ohne KI, Vorschau, **⬇ HTML- und SVG-Download-Buttons**
- **Diagramme-Tab:** Liste aller erzeugten Diagramme mit Öffnen, HTML-/SVG-Download,
  Löschen und **✏️ Überarbeiten** (bestehendes Diagramm per KI nachbearbeiten —
  Änderungswunsch eingeben, es entsteht eine neue `-v2-`-Version, das Original bleibt)
- **Einstellungen-Tab:** KI-Anbieter konfigurieren – **OmniRoute** (lokal, vorbelegt),
  **OpenRouter** oder benutzerdefiniert (OpenAI-kompatibel): Basis-URL, API-Key, Modell
- Keine Abhängigkeiten: nur Python 3 (Standardbibliothek), systemd-Service inklusive

## LXC auf Proxmox (Community-Script-Stil)

Auf dem **Proxmox-Host als root** ausführen (lädt Installer + Tarball direkt von GitHub):

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/HatchetMan111/DiagrammDesign/main/diagram-studio-install.sh)"
```

Der Installer erkennt automatisch: freie VMID (`nextid`), Storage (bevorzugt
`local-lvm`), Debian-12-Template (lädt es per `pveam`, falls fehlend), DHCP an
`vmbr0`. Optional per Env anpassbar:

```bash
VMID=200 HN=diagram-studio CORES=2 MEMORY=2048 DISK=8 PASSWORD=geheim \
bash -c "$(curl -fsSL https://raw.githubusercontent.com/HatchetMan111/DiagrammDesign/main/diagram-studio-install.sh)"
```

Standard-Tarball ist das GitHub-Archiv (`.../archive/refs/heads/main.tar.gz`).
LAN-Alternative: eigenen Artefakt-Server nutzen, z. B.
`ARTIFACT_BASE=http://192.168.178.51:8090` (erwartet dort `diagram-studio.tar.gz`)
oder direkt `TARBALL_URL=<url>` setzen.

Danach im Browser `http://<LXC-IP>:8123` öffnen → oben **Einstellungen (KI)** →
Anbieter wählen, Key + Modell eintragen, speichern.

## Manuell starten (zum Testen)

```bash
python3 server.py 8123
# → http://localhost:8123
```

## Dateien

| Datei | Zweck |
|---|---|
| `server.py` | Backend (stdlib-only): UI, Settings-/Models-/Test-API, LLM-Proxy, Diagramm-Tabelle, Download |
| `index.html` | Web-UI (Erstellen + Diagramm-Tabelle + Einstellungen mit Modell-Suche und Verbindungstest) |
| `favicon.svg` | Browser-Tab-Icon (dunkles Quadrat, coral Knoten) |
| `diagram-studio.service` | systemd-Unit (Port 8123) |
| `diagram-studio-install.sh` | LXC-Installer für den Proxmox-Host |
| `skill/` | diagram-design Referenzen + Templates (wird an die KI als Stil-Kontext gegeben) |
| `generated/` | erzeugte Diagramme (wird ausgerollt, Inhalt nicht versioniert) |
