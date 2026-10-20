# Beamer-Ansicht

In der Verwaltung oben die Sitzung auswählen. Unter **Übersicht → Beamer** eine laufende Partie oder die Rangliste auswählen und **Übertragen** anklicken. Anschließend **Beamer öffnen** oder den Link auf dem Beamer-Rechner öffnen. **Vollbild** vergrößert die Anzeige; Escape beendet den Vollbildmodus.

Der Link bleibt beim Wechsel zwischen Partien und Rangliste derselben Sitzung unverändert. Der Beamer übernimmt Änderungen ohne Neuladen. Jede Sitzung hat einen eigenen Link. Nach Spielende wird automatisch die Rangliste angezeigt; eine Revanche oder andere Partie wird erst nach bewusster Auswahl übertragen. Pausen und Wartezeiten auf Wiederverbindungen werden angezeigt. Die Rangliste umfasst die 20 Spieler mit den meisten Credits, ohne gesperrte Profile.

Inhaber und Administratoren können ihre verfügbaren Sitzungen auswählen; Spielleiter nur ihre zugewiesenen Sitzungen. Spielerkonten brauchen für ihre eigenen Sitzungen sowohl „Spielregeln ändern“ (`manage_games`) als auch „Ergebnisse ansehen“ (`view_results`). Sonst bleibt der Bereich verborgen und die API weist Änderungen ab.

Die Beamer-Seite ist rein passiv. Sie öffnet keinen Spieler-WebSocket und benötigt keinen Spieler- oder Verwaltungslogin. Der 64 Zeichen lange Zufallslink ist eine widerrufbare Freigabe: Jeder mit diesem Link kann die ausgewählten Inhalte ansehen. Der Schlüssel steht im URL-Fragment und wird nur im Header `X-Projector-Token` an die Lese-API `/api/beamer` übergeben. Sitzungscodes, Kontoadressen, Profil-Zugangsdaten und interne Raumkennungen sind nicht Bestandteil der öffentlichen Antwort. Live-Frames enthalten ausschließlich die gemeinsame Ansicht `0`. Spiele mit verdeckten Informationen sind ausgeschlossen, auch bei direkten API-Aufrufen.

**Übertragung beenden** widerruft den Link. Eine erneute Freigabe erzeugt einen neuen Schlüssel. Sitzungsende und Serverneustart beenden die Freigabe ebenfalls. Die Auswahl und der Schlüssel liegen nur im Arbeitsspeicher; keine neue Datenbank oder dauerhafte Speicherung. Die Verwaltungsaktion wird ohne Freigabeschlüssel protokolliert. Bei Verbindungsfehlern entfernt die Seite das alte Bild und versucht die Verbindung erneut; ein widerrufener Link bleibt geschlossen.

Tests: `python -m unittest discover -s tests -p test_projector.py -v`. Geprüft werden Freigabe, Schlüsselwechsel, Sitzungstrennung, Rechte/CSRF, Pausen, Spielende, verdeckte Ansichten und der öffentliche Datenumfang.
