import socket
import time

class kOSProcessor:
  def __init__(self, host="192.168.20.104", port=1123, cpu=1, timeout=5):
    self.host = host
    self.port = port
    self.cpu = cpu
    self.timeout = timeout

    self.sock = None

    self.connect()

  def connect(self):
    self.sock = socket.create_connection((self.host, self.port), self.timeout)

    self.read_some(1.0)

    self.send_line(str(self.cpu))
    time.sleep(0.5)


  def read_some(self, timeout=0.5):
    self.sock.settimeout(timeout)
    chunks = []

    while True:
      try:
        data = self.sock.recv(4096)
        if not data:
          break
        chunks.append(data)
      except TimeoutError:
        break
      except socket.timeout:
        break

    return b"".join(chunks).decode("utf-8", errors="replace")


  def send_line(self, line):
    self.sock.sendall((line + "\r\n").encode("utf-8"))

  def run_script(self, script, *args):
    self.send_line(f"RUNPATH(\"0:/boot/{script}.ks {" ".join(args)}\").")

# kos = kOSProcessor()
# kos.connect()
# kos.run_script("rocket")
