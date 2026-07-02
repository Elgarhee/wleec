export PATH="/wzvenv/bin:$PATH"
echo "=== PATH is: $PATH ==="
echo "=== Contents of /wzvenv/bin ==="
ls -la /wzvenv/bin || true
echo "=== Searching for stormtorrent ==="
find / -name "stormtorrent" 2>/dev/null || true
echo "=== Searching for qbittorrent ==="
find / -name "*qbittorrent*" 2>/dev/null || true
source .venv/bin/activate && python3 update.py && python3 -m bot
