# Revanche, Abstimmung und Warteraum

Beim Erstellen einer Sitzung kann die Spielleitung „Mit Warteraum starten“ aktivieren, sowohl im einfachen Spielerkonto als auch in der Verwaltung. Jeder verbundene Spieler meldet sich bereit. Ab zwei verbundenen Spielern und sobald alle bereit sind, kann die Spielleitung die Sitzung freigeben. Erst dann sind Herausforderungen und Matchstarts möglich. Die Freigabe öffnet die gewohnte Spielauswahl; sie teilt keine Gegner automatisch zu. Neue Sitzungen ohne diese Option funktionieren sofort wie bisher.

Nach einer beendeten Partie mit zwei, drei oder fünf bis acht Teilnehmern können dieselben Spieler eine Revanche im selben Minispiel zusagen. Erst wenn alle zugesagt haben, startet die nächste Partie. Die Einladung verfällt nach 60 Sekunden.

Nach einer regulär beendeten Viererpartie beginnt automatisch eine Abstimmung zwischen den freigegebenen Spielen für vier Teilnehmer: Neon Tail (Tron), Bomber und Jump’n’Bump sowie Zeichnen & Raten (mindestens vier Spieler). Alle vier müssen innerhalb von 30 Sekunden abstimmen. Die meisten Stimmen entscheiden; bei Gleichstand wird zwischen den gleichauf liegenden Spielen gelost. Eine Stimme kann bis zur Entscheidung geändert werden. Vier Spieler in der Lobby allein lösen keine Abstimmung aus.

„Gruppe verlassen“, ein Verbindungsabbruch, eine Sperre oder der Start einer anderen Partie schließt das gemeinsame Angebot für alle. Nach administrativem Abbruch, technischen Fehlern oder einer unvollständig beendeten Viererpartie entsteht keine Abstimmung. Die bestehende Wiederverbindung während laufender Partien bleibt erhalten. Eine pausierte Sitzung erlaubt keine neuen Zusagen; abgelaufene Angebote werden geschlossen.

Bereitschaft, Angebote und Stimmen liegen nur im Arbeitsspeicher der jeweiligen Sitzung und werden nicht als Kontodaten oder Verlauf gespeichert. Die Warteraum-Option und ihre Freigabe werden in den vorhandenen Sitzungsregeln gespeichert. Ein Neustart setzt die Bereitschaft zurück; bereits freigegebene Sitzungen bleiben freigegeben. Die Freigabe wird wie andere Verwaltungsaktionen protokolliert.

Prüfung: `python -m unittest discover -s tests -p test_round_flow.py -v`. Die Tests verwenden temporäre Sitzungen und echte WebSocket-Verbindungen einschließlich Match-Unterprozessen. Sie prüfen unter anderem die Startsperre, Freigabe, vollständige Zusagen, Mehrheitswahl, Sitzungsgrenzen, Abbruch, Ablauf und erneutes Versuchen nach ausgelasteter Serverkapazität.
