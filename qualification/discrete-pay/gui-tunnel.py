import select,socketserver,threading,time
from resume_host import connect
client=connect()
class Handler(socketserver.BaseRequestHandler):
 def handle(self):
  channel=client.get_transport().open_channel('direct-tcpip',('127.0.0.1',18891),self.request.getpeername())
  try:
   while True:
    ready,_,_=select.select([self.request,channel],[],[],30)
    for origin in ready:
     data=origin.recv(65536)
     if not data:return
     (channel if origin is self.request else self.request).sendall(data)
  finally:channel.close()
class Server(socketserver.ThreadingTCPServer):
 allow_reuse_address=True
 daemon_threads=True
server=Server(('127.0.0.1',18891),Handler)
threading.Timer(1500,server.shutdown).start()
print('GUI tunnel ready: local127.0.0.1:18891 -> pinned SSH -> server127.0.0.1:18891',flush=True)
try:server.serve_forever(poll_interval=.5)
finally:server.server_close();client.close()
