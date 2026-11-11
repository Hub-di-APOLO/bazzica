# Caddy con il modulo DuckDNS, per ottenere il certificato Let's Encrypt con la verifica DNS:
# così non servono le porte 80/443 esterne (restano all'interfaccia del NAS) e la Bazzica
# può stare su una porta qualsiasi, es. https://tuonome.duckdns.org:20443
#
# Costruzione sul NAS:
#   docker build -t caddy-duckdns:locale /mnt/<pool>/apps/bazzica/codice/deploy/truenas/caddy
ARG CADDY_VERSION=2.10
FROM caddy:${CADDY_VERSION}-builder AS costruzione
RUN xcaddy build --with github.com/caddy-dns/duckdns

FROM caddy:${CADDY_VERSION}
COPY --from=costruzione /usr/bin/caddy /usr/bin/caddy
