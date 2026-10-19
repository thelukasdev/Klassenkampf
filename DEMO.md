# Öffentliche Demo

Startseite → **Demo spielen**, direkt `/demo`. Vier gewinnt gegen einen Bot, ohne Konto, Code, WebSocket oder registrierte Sitzung. Spielfeld und Bot laufen ausschließlich im Browser; kein globaler Raum und keine serverseitigen Ergebnisse, Spielerprofile oder Replays. Jede Seite hat ihren eigenen Zustand. Kein lokales Speichern des Spielstands; der bestehende Cookie-Hinweis nutzt weiterhin seine normale Bestätigung.

Bot: eigener Web Worker, unmittelbare Gewinne/Abwehr sowie begrenzte Alpha-Beta-Suche (Tiefe 4, maximal 12000 Knoten/120 ms). Ersatz bei fehlender Worker-Unterstützung bzw. Fehler mit kleinerer Suche; maximal zwei Sekunden Worker-Wartezeit. Veraltete Antworten werden über Anfragekennungen verworfen. Neue Runde/Seitenwechsel/Ende terminieren Worker und ausstehende Bot-Timer. Nach zwei Minuten ohne Spieleraktion endet die Runde. Erneutes Öffnen aus dem Browser-Zurück-Cache startet eine frische Seite.

Steuerung: Spaltentasten antippen, Tasten 1–7 oder Pfeile und Enter. Vier waagerecht, senkrecht oder diagonal gewinnen. Eine volle Spalte nimmt keine weiteren Steine an; ein volles Feld ohne Viererreihe ist unentschieden. Bot und Mensch setzen abwechselnd. Keine Änderungen an normalen Minispiel-Engines, Sitzungsrechten oder dem Sitzungslimit.
