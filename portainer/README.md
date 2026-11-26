Portainer is the one stack not managed by Portainer itself. Run it from this directory:

```
docker compose up -d
```

Stop it cleanly:

```
docker compose down
```

The UI is HTTPS only on port 9443 (also served as the `svc:portainer` Tailscale Service).
