# Grafana Cloud

Die Anwendung stellt unter /internal/metrics begrenzte technische Messwerte bereit. Der Zugriff benötigt den vorhandenen KLASSENKAMPF_STATUS_TOKEN; der Reverse Proxy muss /internal/* öffentlich sperren.

Ein kleiner Python-Prozess überträgt alle 60 Sekunden Messwerte über Grafana Clouds Influx-HTTP-Schnittstelle. Er verwendet das vorhandene Anwendungsimage, maximal 32 MiB RAM und 0,1 CPU, keine zusätzliche Datenbank und keine öffentlichen Ports. Der erste Linux-Test benötigte etwa 24 MiB RSS. Die gesamte RAM-Reserve des Hosts muss weiterhin überwacht werden.

## Einrichtung

1. Grafana Cloud Free anlegen. Im Stack die InfluxDB-Verbindungsdetails öffnen.
2. Eine Access Policy nur für diesen Stack mit metrics:write erstellen. Token mit begrenzter Laufzeit ausstellen.
3. Außerhalb des Repositorys ein geschütztes Verzeichnis anlegen (Standard: ../klassenkampf-private/monitoring, Modus 0700). Dort grafana-cloud.json und status-token ablegen. Die Dateien müssen für Container-UID 10001 lesbar sein. Niemals Tokens committen.
4. grafana-cloud.json enthält endpoint (HTTPS-Host aus dem Cloud-Portal mit /api/v1/push/influx/write), instance_id (als String) und token. status-token enthält denselben Wert wie KLASSENKAMPF_STATUS_TOKEN der Anwendung.
5. sh monitoring/cloud-compose.sh up -d --no-deps cloud-metrics startet ausschließlich den Sender. Der Sender startet nach einem Serverneustart automatisch. Bei der ersten Einrichtung Speicherreserve und erfolgreiche Übertragung prüfen; zum Test kann restart vorübergehend auf no gesetzt werden.
6. monitoring/grafana/dashboards/klassenkampf.json über Dashboards → New → Import importieren; die eigene Grafana-Cloud-Prometheus-Datenquelle auswählen.
7. KLASSENKAMPF_MONITORING_URL auf die HTTPS-Dashboardadresse ohne Token oder Queryparameter setzen und die Anwendung neu erstellen. Inhaber und Administratoren sehen den Link unter Serverstatus. Grafana verwendet seine eigene Kontoanmeldung.

## Daten und Warnungen

Übertragen werden CPU-Zeiten, verfügbarer RAM/Festplattenspeicher, Anzahl Spieler/Sitzungen/Partien/Prozesse, Verbindungen, HTTP-Laufzeiten und Fehlerzähler. Keine Namen, E-Mail-Adressen, Sitzungscodes, URLs, Tickettexte oder Spielinhalte. Feste Labelmengen begrenzen die Anzahl der Zeitreihen.

Die Warnungstabelle prüft beim Öffnen/Aktualisieren Senderausfall, nicht erreichbare Anwendung, weniger als 15 % freien RAM/Festplattenspeicher, CPU über 85 %, kürzliche Prozessfehler und gehäufte HTTP-Fehler. Es sind Dashboard-Warnungen, keine Hintergrundbenachrichtigungen. Es werden keine E-Mails verschickt. Mehrere Messpunkte sind für Raten erforderlich. Free-Aufbewahrungsdauer und Kontingente gelten gemäß Grafana-Vertrag.

Ein komplett ausgefallener VPS kann keine Werte senden: deshalb zeigt das Dashboard das Alter des letzten Messwerts und warnt bei ausbleibendem Heartbeat. Daten können bis zur nächsten Übertragung veraltet sein. Der Sender hält keinen lokalen Rückstau.

## Betrieb

sh monitoring/cloud-compose.sh logs --tail 10 cloud-metrics
sh monitoring/cloud-compose.sh stop cloud-metrics

Token vor Ablauf erneuern und nur die private Datei ersetzen; anschließend Sender neu erstellen. Fehlermeldungen enthalten keine Tokens. Lokale Grafana-/Prometheus-Container werden für diese Einrichtung nicht benötigt und sollen auf kleinen VPS gestoppt bleiben.
