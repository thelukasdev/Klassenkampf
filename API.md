# Klassenkampf API v1

Swagger UI: /api/docs — OpenAPI 3.0: /api/openapi.json.

GET /api/v1/status und GET /api/v1/games sind öffentlich. GET /api/v1/sessions liefert maximal 200 anonymisierte Sitzungsstatus mit Spieler- und Partiezahlen. GET /api/v1/results summiert abgeschlossene Partien je Spiel in den aktuell geladenen Sitzungen. Keine Ranglisten, Namen, Konto-Informationen, Sitzungscodes oder Spielinhalte. Keine Schreiboperationen.

## Schlüssel

Geschützte Endpunkte erfordern Authorization: Bearer <Integrationsschlüssel>. Die API verwendet ausschließlich APP_DIR/external-api.key (im Container /data/external-api.key), niemals den Verwaltungs- oder Status-Token. Datei mit einem zufälligen URL-sicheren Schlüssel (mindestens 40 Zeichen), Containerbenutzer 10001 und Modus 0600 anlegen. Nicht im Repository speichern. Fehlende Datei deaktiviert geschützte Endpunkte mit 503. Ersetzen oder Löschen widerruft den alten Schlüssel bei der nächsten Anfrage. Ein gemeinsamer Schlüssel gewährt ausschließlich den dokumentierten Lesezugriff; noch keine benutzerbezogenen Schlüssel.

Swagger: Authorize öffnen und den Schlüssel eintragen. Swagger speichert die Autorisierung nicht dauerhaft. Alle Swagger-Dateien werden lokal ausgeliefert (swagger-ui-dist 5.33.3, Apache-2.0; Lizenz und Herkunft unter static/swagger). Keine externe Validierung oder externen Skripte.

Anfragelimits gelten je Anwendungsprozess, in getrennten Minutenfenstern: 600 öffentlich, 120 autorisiert, 60 ungültige Authentifizierungen. 429 enthält Retry-After: 60. Bei Neustart werden Limits zurückgesetzt. Keine browserübergreifende CORS-Freigabe; serverseitige Clients können direkt aufrufen.

Die API ist Teil des bestehenden Servers: kein zusätzlicher Dienst, Container oder offener Port. Antworten sind JSON mit Cache-Control: no-store. Die öffentliche Statusroute ist ein einfacher API-Lebenscheck, keine vollständige Netzwerkdiagnose. Für den öffentlichen Netzwerkverlauf bleibt /status zuständig.
