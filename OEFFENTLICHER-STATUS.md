# Öffentlicher Netzwerkstatus

URL: https://spiele.example.org/status. Ohne Anmeldung erreichbar; Footer-Links auf Spielseite, Verwaltungsanmeldung, Verwaltungsoberfläche und Statusseite. Jede Sitzungskarte der Verwaltung verlinkt ihren öffentlichen Statusverlauf. Öffentliche Sitzungen tragen eine aus ihrer internen ID abgeleitete Statuskennung; weder Beitrittscode noch interner Name oder Spielername wird übertragen.

## Prüfung und Verlauf
Ein eigenständiger Docker-Dienst `status` prüft alle 15 Sekunden:
- öffentlichen HTTPS-Zugang über die Domain inklusive normaler Zertifikatsprüfung;
- interne HTTP-Antwort der Spielanwendung;
- echten WebSocket-Handshake inklusive Accept-Prüfung;
- Erreichbarkeit des SQLite-Spielstandspeichers;
- alle Sitzungen: bereit, laufend, bewusst pausiert, beeinträchtigt oder beendet.

Aggregierte Online-Spieler- und Partiezahlen sind öffentlich. Sitzungsprozesse mit kürzlich aufgetretenem Fehler gelten als beeinträchtigt, bis ein Prozess wieder erfolgreich läuft oder die fünfminütige Fehleranzeige ausläuft. Anmeldedaten, Rollen, Spielstände, Ergebnistabellen, Browser-Tokens und Server-IP werden nicht in den öffentlichen Feed kopiert.

Zustandswechsel und Tagesaggregate liegen dauerhaft in einer eigenen SQLite-Datenbank im Docker-Volume `klassenkampf_status_data`. Keine automatische Löschung: Der grafische Zeitraum umfasst 7/30/90 Tage; ältere Zustandswechsel bleiben gespeichert und über die paginierte API abrufbar. Die Oberfläche zeigt nur die letzten sechs Einträge. Beim Dienstneustart werden die vorhandenen Daten weiterverwendet. Tageswerte verwenden UTC, Ereigniszeiten die lokale Browserzeit. Werte werden beim Lesen um das laufende Messintervall ergänzt.

Der Verlauf beginnt bei der Einrichtung. Der Zustand zwischen zwei erfolgreichen Proben wird zeitlich näherungsweise dem vorher beobachteten Zustand zugerechnet. Liegen mehr als 45 Sekunden zwischen Proben, bleiben nur die ersten 15 Sekunden dem letzten beobachteten Zustand zugeordnet; die restliche Zeit wird explizit als unbekannt erfasst, einschließlich Ereignis im Verlauf. Auch veraltete Daten bei einem laufenden Seitenaufruf werden als unbekannt angezeigt. Kurze Ausfälle zwischen zwei Proben können unentdeckt bleiben; eine lückenlose Beobachtung jeder Millisekunde wird nicht behauptet.

Verfügbarkeit = verfügbare überwachte Sekunden / bekannte überwachte Sekunden. Bereitschaft und absichtliche Pause zählen als erreichbar; beeinträchtigte Zeit und Ausfall gelten nicht als vollständig verfügbar. Unbekannte Zeit wird separat ausgewiesen. Beendete Sitzungen sammeln keine weitere Verfügbarkeitszeit.

## Unabhängigkeit und Grenzen
Der Statusdienst benutzt ein eigenes Volume, einen eigenen Prozess und ein 48-MiB-Containerlimit. Caddy leitet `/status` und `/api/status` direkt zu diesem Dienst weiter. Dadurch bleibt die Statusseite bei Ausfall oder Neustart der Spielanwendung nutzbar. Statusdienst, Caddy und Spielserver liegen auf demselben VPS. Ein Ausfall des VPS, seiner Internetanbindung oder von Caddy kann daher auch die Statusseite unerreichbar machen. Beim Wiederanlaufen wird eine erkannte Überwachungslücke als unbekannt protokolliert. Vollständige externe Ausfallbeobachtung benötigt zusätzlich einen Dienst auf einem zweiten Host.

Der Monitoring-Feed `/internal/status.json` ist mit einem separaten Bearer-Token aus `.env` geschützt und wird in Caddy zusätzlich generell mit 404 blockiert. Nur der Statusdienst erhält dieses Token; der öffentliche API-Endpunkt ist eine reine Leseansicht der freigegebenen Statusdaten.

Neue Installationen: `configure.py` erzeugt auch `KLASSENKAMPF_STATUS_TOKEN`. Bestehende Installationen müssen diesen zufällig setzen, bevor `docker compose up -d --build` ausgeführt wird. Niemals `docker compose down -v` zur normalen Wartung verwenden: Das würde persistente Daten löschen.

## Sicherung
Für ein konsistentes Backup der Statusdaten `sqlite3.Connection.backup()` innerhalb des Statuscontainers verwenden und die erzeugte Datei außerhalb des Containers sichern. Die Spielstand-Sicherung in der Verwaltung ersetzt keine Sicherung des Statusvolumes.

Die Oberfläche zeigt im Statusverlauf ausschließlich die neuesten sechs Ereignisse je gewähltem Bereich. Ältere Ereignisse und Tageswerte bleiben gespeichert.

Spieleranmeldung und Verwaltungsanmeldung werden alle 15 Sekunden durch echte GET-Anfragen an ihre CSRF-Schnittstellen geprüft. Für einen verfügbaren Status muss auch der Spielstandspeicher erreichbar sein; bei Spielern muss zusätzlich die E-Mail-Konfiguration vorhanden sein. Diese Prüfung versendet keine E-Mails und prüft keine Benutzerpasswörter oder die tatsächliche Mailzustellung. Störungen beeinflussen den Gesamtstatus und werden wie bei den übrigen Diensten mit Verlauf erfasst.
