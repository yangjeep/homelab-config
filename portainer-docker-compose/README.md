Running Portainer Docker-compose:
```
docker-compose up
```

Stop docker-compose cleanly:
```
docker-compose stop
docker-compose rm -f
```

Running agent:
```
docker run -d -p 9001:9001 --name portainer_agent --restart=always -v /var/run/docker.sock:/var/run/docker.sock -v /var/lib/docker/volumes:/var/lib/docker/volumes portainer/agent:latest
```


