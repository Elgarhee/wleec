FROM mysterysd/wzmlx:v3

WORKDIR /usr/src/app

RUN chmod 777 /usr/src/app
RUN rm -f /usr/bin/qbittorrent-nox /usr/local/bin/qbittorrent-nox /usr/bin/stormtorrent /usr/local/bin/stormtorrent
RUN uv venv --system-site-packages

COPY requirements.txt .
RUN uv pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["bash", "start.sh"]
