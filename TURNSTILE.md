# Turnstile bei der Registrierung

Nur die Registrierung eines Spielerkontos lädt das Managed-Widget. Die Anmeldung, Gastteilnahme und laufende Spiele verwenden es nicht.

Zur Aktivierung im Datenverzeichnis neben `admin.sqlite3` eine private Datei `turnstile.json` mit den Feldern `sitekey` und `secret` hinterlegen. Beide Werte stammen aus dem eigenen Cloudflare-Widget; dessen Hostnamen auf die öffentliche Spieladresse beschränken. Die Datei nur für den Anwendungsnutzer lesbar halten (0600) und den Dienst neu starten. Der öffentliche Schlüssel wird über den CSRF-Konfigurationsabruf bereitgestellt; der geheime Schlüssel bleibt auf dem Server. Ohne Konfigurationsdatei ist die Integration für lokale Installationen ausgeschaltet; eine unvollständige Konfiguration verhindert den Start.

Der Server validiert jedes Registrierungstoken über Cloudflares Siteverify-API und prüft Erfolg, Hostname und Aktion `register`. Fehlende Tokens, ungültige Antworten und nicht erreichbare Prüfungen geben die Registrierung nicht frei. Cloudflare prüft Ablauf und Einmalverwendung. Nach einem Registrierungsversuch wird das Widget zurückgesetzt.

Tests verwenden ausschließlich isolierte Konfigurationen und simulierte Prüfantworten. Produktive Geheimnisse und Konfigurationsdateien gehören nicht ins Repository.
