# Running the demo

The demo is one folder of static files, sent through a named Cloudflare tunnel from this Mac. No process holds a key.

Start (from the repository root):

    nohup /usr/bin/env -i PATH=/usr/bin:/bin /usr/bin/python3 -m http.server 8791 --bind 127.0.0.1 --directory "$PWD/web/dist" > runs/static_server.log 2>&1 &
    nohup cloudflared tunnel --config deploy/cloudflared.yml run permit-engine > runs/tunnel.log 2>&1 &
    caffeinate -dims -t 14400 &

Stop:

    pkill -f 'http.server 8791'; pkill -f 'cloudflared tunnel --config deploy'; pkill caffeinate

Pass `--config deploy/cloudflared.yml` to every `cloudflared tunnel` command, including `route dns`. Without it, `cloudflared` takes the tunnel from `~/.cloudflared/config.yml`, which names a different tunnel.

After a new `make-export`, run `npm run build` in `web/`. The server then serves the new files with no restart.
