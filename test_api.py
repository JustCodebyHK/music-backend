import uvicorn
from main import app
import threading
import time
import requests

def run_server():
    uvicorn.run(app, host='127.0.0.1', port=8001, log_level='error')

thread = threading.Thread(target=run_server, daemon=True)
thread.start()
time.sleep(3)

print("Testing stream_url endpoint...")
try:
    r = requests.get('http://127.0.0.1:8001/api/stream_url/ParFA9QU5EM', timeout=10)
    print('stream_url:', r.status_code, r.json())
except Exception as e:
    print('Error:', e)

print("Testing download endpoint...")
try:
    r = requests.get('http://127.0.0.1:8001/api/download/ParFA9QU5EM', stream=True, timeout=10)
    print('download:', r.status_code)
    if r.status_code == 200:
        print('  Content-Type:', r.headers.get('Content-Type'))
        print('  Content-Disposition:', r.headers.get('Content-Disposition'))
        # Read some data to verify streaming works
        chunk = next(r.iter_content(chunk_size=1024))
        print('  First chunk size:', len(chunk) if chunk else 0)
except Exception as e:
    print('Download Error:', e)