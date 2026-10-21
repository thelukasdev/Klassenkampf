# Cloudflare-Betrieb

## Direkten Webzugriff sperren

Die Produktionsinstallation beschränkt eingehende Webverbindungen auf die offiziellen
Cloudflare-Netze (IPv4 und IPv6). Die eigene nftables-Tabelle `inet kk_origin`
filtert TCP/UDP 80 und 443 auf dem öffentlichen Interface **vor Docker-DNAT**.
SSH, interne Containerkommunikation und ausgehende Verbindungen bleiben erreichbar.
Ein bloßes INPUT-Limit würde veröffentlichte Docker-Ports nicht vollständig schützen.

Die drei Dateien unter `deploy/cloudflare/` sind eine Vorlage für Linux mit nftables:

1. Öffentliches Interface prüfen (`ip route`), `eth0` in der Vorlage gegebenenfalls ändern.
2. Cloudflare-Netze mit <https://www.cloudflare.com/ips/> abgleichen.
3. `cloudflare-origin.nft` nach `/etc/klassenkampf/` kopieren, das Shellskript als
   `/usr/local/sbin/kk-origin-firewall` installieren, Modus 750.
4. Unit nach `/etc/systemd/system/kk-origin-firewall.service` kopieren und mit
   `systemctl daemon-reload` laden.
5. Regeln mit `nft --check --file /etc/klassenkampf/cloudflare-origin.nft` prüfen.
   Vor Aktivierung eine zweite SSH-Sitzung und zeitgesteuerten Rollback bereithalten.
6. `systemctl enable --now kk-origin-firewall.service` aktivieren; Erreichbarkeit
   durch Cloudflare und Sperre direkter HTTP/HTTPS-Verbindungen von extern prüfen.

Das Skript ersetzt nur seine eigene Tabelle atomar. Es leert niemals das gesamte
Regelwerk. Die Unit lädt die Regeln beim Systemstart vor Docker. Nach Änderungen:
`systemctl reload kk-origin-firewall.service`.

Rollback: `systemctl disable kk-origin-firewall.service` und
`nft delete table inet kk_origin`. Das Stoppen allein entfernt bewusst keine Regeln.
Bei Netzwerkänderungen oder geänderten Cloudflare-Netzen muss die Liste angepasst werden.
Der Domain-Datensatz muss weiterhin als Proxy aktiv sein. Zertifikatsverlängerungen
benötigen eine funktionierende HTTP-01-Prüfung über den Proxy; Port 80 bleibt für
Cloudflare offen. Ein Wechsel auf DNS-only macht die Website absichtlich unerreichbar.

Diese Regel beschränkt den Zugriff auf die Cloudflare-Netze; sie authentifiziert
nicht eine bestimmte Cloudflare-Zone. Für eine weitere Absicherung kommen ein
eigener Origin-Pull-Clientschlüssel oder Cloudflare Tunnel infrage.
