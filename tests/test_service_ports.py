import errno,socket,threading,time
import pytest
from pathoreason.service_ports import wait_until_bindable


def listener():
    s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',0));s.listen();return s


def test_restart_waits_for_delayed_port_release():
    s=listener();port=s.getsockname()[1]
    timer=threading.Timer(.15,s.close);timer.start()
    try:wait_until_bindable(port,timeout=1)
    finally:timer.join();s.close()


def test_occupied_port_times_out_without_touching_owner():
    with listener() as s:
        port=s.getsockname()[1];start=time.monotonic()
        with pytest.raises(OSError) as exc:wait_until_bindable(port,timeout=.2)
        assert exc.value.errno==errno.EADDRINUSE and time.monotonic()-start<1
        with socket.create_connection(('127.0.0.1',port),timeout=.2):pass
