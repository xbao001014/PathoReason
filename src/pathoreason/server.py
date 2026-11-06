"""Serve on explicit loopback/Tailscale IPv4 sockets, never wildcard interfaces."""
import ipaddress
import socket


def listeners(config):
    hosts = config.get('api_hosts', ['127.0.0.1'])
    if not isinstance(hosts, list) or not hosts or len(set(hosts)) != len(hosts):
        raise ValueError('api_hosts must be a nonempty list of distinct IPv4 addresses')
    for host in hosts:
        address = ipaddress.IPv4Address(host)
        if not (address.is_loopback or address in ipaddress.IPv4Network('100.64.0.0/10')):
            raise ValueError('API listener must be loopback or a Tailscale address')
    sockets = []
    try:
        for host in hosts:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sockets.append(sock)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, int(config['api_port'])))
        return sockets
    except BaseException:
        for sock in sockets:
            sock.close()
        raise


def main():
    import uvicorn
    from .settings import settings
    cfg = settings()
    sockets = listeners(cfg)
    try:
        uvicorn.Server(uvicorn.Config('pathoreason.api:app', port=cfg['api_port'],
            proxy_headers=False, timeout_graceful_shutdown=2)).run(sockets=sockets)
    finally:
        for sock in sockets:
            sock.close()


if __name__ == '__main__':
    main()
