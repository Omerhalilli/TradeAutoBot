import zmq
import json

ctx = zmq.Context()
sock = ctx.socket(zmq.REQ)
sock.setsockopt(zmq.RCVTIMEO, 3000)
sock.setsockopt(zmq.SNDTIMEO, 3000)
sock.connect("tcp://127.0.0.1:5555")

print("Sending PING...")
sock.send_json({"action": "PING"})

try:
    reply = sock.recv_json()
    print("REPLY RECEIVED:", reply)
except Exception as e:
    print("Error receiving:", e)

sock.close()
ctx.term()
