# Diagram-Studio

Web-UI zum Erstellen von Diagrammen nach dem **diagram-design** Skill-System
(40 Diagrammtypen, editorial Design, self-contained HTML + SVG).

- **Erstellen-Tab:** Beschreibung eingeben, Typ wählen (Architektur, Flowchart, Sequenz, …),
  per KI erzeugen oder Schnell-Entwurf ohne KI, Vorschau, **⬇ HTML-Download-Button**
- **Einstellungen-Tab:** KI-Anbieter konfigurieren – **OmniRoute** (lokal, vorbelegt),
  **OpenRouter** oder benutzerdefiniert (OpenAI-kompatibel): Basis-URL, API-Key, Modell
- Keine Abhängigkeiten: nur Python 3 (Standardbibliothek), systemd-Service inklusive

## LXC auf Proxmox (Community-Script-Stil)

Auf dem **Proxmox-Host als root** ausführen:

```bash
bash -c "$(curl -fsSL http://192.168.178.51:8090/diagram-studio-install.sh)"
```

Der Installer erkennt automatisch: freie VMID (`nextid`), Storage (bevorzugt
`local-lvm`), Debian-12-Template (lädt es per `pveam`, falls fehlend), DHCP an
`vmbr0`. Optional per Env anpassbar:

```bash
VMID=200 HN=diagram-studio CORES=2 MEMORY=2048 DISK=8 PASSWORD=geheim \
bash -c "$(curl -fsSL http://192.168.178.51:8090/diagram-studio-install.sh)"
```

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
| `server.py` | Backend (stdlib-only): UI, Settings-API, LLM-Proxy, Download |
| `index.html` | Web-UI (Erstellen + Einstellungen) |
| `diagram-studio.service` | systemd-Unit (Port 8123) |
| `diagram-studio-install.sh` | LXC-Installer für den Proxmox-Host |
| `skill/` | diagram-design Referenzen + Templates (wird an die KI als Stil-Kontext gegeben) |
| `generated/` | erzeugte Diagramme (wird ausgerollt, Inhalt nicht versioniert) |
