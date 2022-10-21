Need to copy/link the config files to /var/lib/docker/volumes/<>/_data

```
ln -s ~/homelab-config/docker-compose_grafana-loki/loki-config.yml /var/lib/docker/volumes/grafana-loki_loki/_data/loki-config.yml
ln -s ~/homelab-config/docker-compose_grafana-loki/promtail-config.yml /var/lib/docker/volumes/grafana-loki_promtail/_data/promtail-config.yml
```
