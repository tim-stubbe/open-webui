# Open WebUI Custom – To-do

## Sprachchat

- [x] Vorhandene lokale Modelle auf kurze deutschsprachige Antworten und Laufzeit testen.
- [x] OmniRoute-Kombi `Sprachchat-lokal` mit `ollama-local/gemma3:4b` anlegen.
- [ ] Open WebUI-Sprachmodus fest auf `Sprachchat-lokal` routen, während Textchat weiter seine eigene Kombi nutzt.
- [ ] Streaming und Abbruch beim Sprechen prüfen; Ziel: schnelle erste hörbare Antwort statt Warten auf den vollständigen Text.
- [ ] Sprach-Prompt auf kurze, natürliche Antworten ohne Listen optimieren.
- [ ] Optional ein aktuelles 3–4B-Modell gegen Gemma 3 testen, falls die Qualität im Alltag nicht reicht.

### Messergebnisse vom 8. September 2026

| Modell | Vollständige Kurzantwort | Bewertung |
|---|---:|---|
| `gemma3:4b` | 7,36 s | Beste Mischung aus Tempo und brauchbarem Deutsch |
| `phi4-mini` | 10,90 s | Schnell, aber inhaltlich widersprüchlich |
| `qwen3:8b` ohne Denkmodus | 11,67 s | Brauchbar, für Sprachchat unnötig schwer |

## Computer Use

- [x] Eigene Open-WebUI-Erweiterung für lokale Computersteuerung entwerfen.
- [x] Computer-Use-Dienst als getrennten lokalen Prozess auf dem Mac vorbereiten.
- [x] Sichere, tokenbasierte Verbindung zwischen Open WebUI und dem Mac-Dienst vorbereiten.
- [x] Werkzeuge auf Bildschirm lesen, klicken, tippen und scrollen begrenzen.
- [x] Browseraktionen technisch auf HTTP(S), feste Aktionen und vorhandene CSS-Selektoren beschränken.
- [ ] Zugriffe zusätzlich auf eine konfigurierbare Liste erlaubter Apps und Seiten beschränken.
- [ ] Für sensible oder irreversible Aktionen eine Bestätigung verlangen.
- [ ] Werkzeugaufrufe und Ergebnisse protokollieren, ohne Passwörter oder andere Secrets zu speichern.
- [x] Eingabe-Stopp über `COMPUTER_USE_ALLOW_INPUT` und feste Zeitlimits einbauen.
- [ ] Zuerst in einer Testumgebung prüfen, danach in die TrueNAS-Installation übernehmen.

## Pflege des Forks

- [ ] Eigenes Container-Image bauen und getrennt von der laufenden Open-WebUI-Installation testen.
- [ ] Änderungen klein und nachvollziehbar halten.
- [ ] Sicherheitsupdates aus dem offiziellen Open-WebUI-Repository gezielt übernehmen.
