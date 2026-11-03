"""Bounded wait for socket release; never signals a port's owner."""
import errno
import socket
import time


def wait_until_bindable(port:int,timeout:float=5.0):
    deadline=time.monotonic()+timeout
    while True:
        try:
            with socket.socket() as sock:
                sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
                sock.bind(('127.0.0.1',port))
            return
        except OSError as exc:
            if exc.errno!=errno.EADDRINUSE or time.monotonic()>=deadline:
                raise
            time.sleep(min(.1,max(0,deadline-time.monotonic())))
