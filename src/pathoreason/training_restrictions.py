"""Mount-free restrictions for a single reviewed Linux x86-64 worker.

Landlock controls file contents; a default-deny seccomp filter closes ABI-1
truncation gaps, network, new processes, metadata mutation and cross-process
access. This is NOT a PID/mount namespace or a defence against the host/kernel,
GPU-driver exploits, GPU side channels, or file-existence metadata disclosure.
Only the fixed worker and validated pure feature grammar are supported.
Install before importing numerical libraries or creating any thread.
"""
import ctypes as C
import errno
import os
from pathlib import Path
import platform
import re
import resource
import stat
import sys


class _Ruleset(C.Structure):
    _fields_ = [('access', C.c_uint64)]


class _PathRule(C.Structure):
    _layout_ = 'ms'
    _pack_ = 1
    _fields_ = [('access', C.c_uint64), ('parent_fd', C.c_int32)]


class _Compare(C.Structure):
    _fields_ = [('arg', C.c_uint), ('op', C.c_int), ('a', C.c_uint64), ('b', C.c_uint64)]


def _check(result, operation):
    if result < 0:
        raise OSError(C.get_errno(), operation)
    return result


def _seccomp(gpu=False):
    sec = C.CDLL('libseccomp.so.2', use_errno=True)
    sec.seccomp_init.argtypes = [C.c_uint32]; sec.seccomp_init.restype = C.c_void_p
    sec.seccomp_syscall_resolve_name.argtypes = [C.c_char_p]
    sec.seccomp_rule_add_array.argtypes = [C.c_void_p, C.c_uint32, C.c_int, C.c_uint, C.POINTER(_Compare)]
    sec.seccomp_load.argtypes = [C.c_void_p]
    sec.seccomp_release.argtypes = [C.c_void_p]
    ctx = sec.seccomp_init(0x00050000 | errno.EPERM)
    if not ctx: raise RuntimeError('Cannot allocate seccomp filter')
    def rule(name, *conditions, action=0x7fff0000, optional=False):
        number = sec.seccomp_syscall_resolve_name(name.encode())
        if number < 0:
            if optional: return
            raise RuntimeError('Required syscall absent from libseccomp: ' + name)
        values = (_Compare * len(conditions))(*[_Compare(*c) for c in conditions])
        result = sec.seccomp_rule_add_array(ctx, action, number, len(values), values)
        if result < 0: raise OSError(-result, 'Cannot add seccomp rule: ' + name)
    try:
        # Pure computation, file operations further restricted by Landlock,
        # anonymous descriptors, and thread synchronisation. No socket, exec,
        # ptrace, process_vm_*, pidfd_getfd, mount, BPF, keyring or io_uring.
        for name in '''read write readv writev pread64 pwrite64 lseek close dup dup2 dup3
            fstat stat lstat newfstatat statx statfs fstatfs access faccessat readlink readlinkat getdents getdents64
            mmap mprotect munmap mremap brk madvise mincore msync mlock munlock mbind get_mempolicy set_mempolicy
            rt_sigaction rt_sigprocmask rt_sigreturn sigaltstack rt_sigtimedwait
            clock_gettime clock_getres clock_nanosleep gettimeofday time nanosleep
            getpid getppid gettid getuid geteuid getgid getegid getgroups uname sysinfo
            getrlimit getrusage sched_getaffinity sched_get_priority_min sched_get_priority_max sched_yield getrandom
            futex set_robust_list set_tid_address rseq
            poll ppoll select pselect6 pipe pipe2 eventfd eventfd2 epoll_create epoll_create1 epoll_ctl epoll_wait epoll_pwait
            fsync fdatasync flock ftruncate
            mkdir mkdirat rmdir unlink unlinkat rename renameat renameat2
            chdir fchdir getcwd umask exit exit_group restart_syscall'''.split():
            rule(name)
        # Avoid F_SETOWN/F_SETSIG and filesystem-mutating IOCTL families.
        for operation in (0, 1, 2, 3, 4, 5, 6, 7, 1030):
            rule('fcntl', (1, 4, operation, 0))
        rule('ioctl', (1, 4, 0x5451, 0))  # FIOCLEX: close-on-exec, no file mutation
        if gpu:
            # CUDA probes an optional local driver service. An unconnected Unix
            # descriptor grants no communication. All connect/bind/send/listen
            # operations remain denied; REFUSED permits its direct-device path.
            rule('socket', (0, 4, 1, 0), (1, 7, 0xf, 5), (2, 4, 0, 0))
            # CUDA's UVM listener binds an abstract Unix address. The launcher
            # MUST establish a private network namespace first. Pathname socket
            # creation is denied by Landlock MAKE_SOCK; all connects are denied.
            for operation in ('bind', 'listen', 'accept', 'accept4', 'getsockopt', 'getsockname', 'getpeername', 'sendmsg', 'recvmsg'):
                rule(operation)
            rule('setsockopt', (1, 4, 1, 0), (2, 4, 16, 0))  # SOL_SOCKET / SO_PASSCRED
            rule('ioctl', (1, 7, 0xff00, 0x4600))  # NVIDIA RM ioctl type 'F'
            rule('ioctl', (1, 3, 255, 0))          # UVM base commands
            for command in (0x30000001, 0x30000002):
                rule('ioctl', (1, 4, command, 0))
        rule('connect', action=0x00050000 | errno.ECONNREFUSED)
        # ABI 1/2 do not control truncate. Even on newer kernels the strict
        # policy denies path truncate and read-only O_TRUNC globally.
        # WRONLY/RDWR O_TRUNC still requires Landlock WRITE_FILE on that path.
        # ftruncate requires an already writable FD: FD hygiene plus Landlock
        # ensure only the dedicated output/stdio/device FDs can be writable.
        for name, arg in [('open', 1), ('openat', 2)]:
            for mode in (os.O_WRONLY, os.O_RDWR):
                rule(name, (arg, 7, os.O_ACCMODE, mode))
            rule(name, (arg, 7, os.O_ACCMODE | os.O_TRUNC, os.O_RDONLY))
        rule('openat2', action=0x00050000 | errno.ENOSYS, optional=True)
        rule('clone3', action=0x00050000 | errno.ENOSYS, optional=True)
        # Only pthread-style threads in this process, never forked children or
        # a new namespace. Reject all namespace flags and nonzero exit signal.
        required = 0x100 | 0x800 | 0x10000  # VM | SIGHAND | THREAD
        namespaces = 0x7e020000 | 0x80      # NEW* flags including NEWTIME
        rule('clone', (0, 7, required | namespaces | 0xff, required))
        rule('tgkill', (0, 4, os.getpid(), 0))
        for pid in (0, os.getpid()):
            rule('prlimit64', (0, 4, pid, 0), (2, 4, 0, 0))  # read own limits only
            rule('sched_setaffinity', (0, 4, pid, 0))
        for option in (15, 16, 21, 39):  # thread name, read-only filter/NNP status
            rule('prctl', (0, 4, option, 0))
        result = sec.seccomp_load(ctx)
        if result < 0: raise OSError(-result, 'Cannot install seccomp filter')
    finally:
        sec.seccomp_release(ctx)


def restrict(*, code, inputs, output, gpu_minor=None, parent_network_namespace=None, shared_read_files=()):
    """Irreversibly restrict this single-threaded disposable subprocess.

    Caller must use -I -S, close all inherited FDs except its dedicated log and
    /dev/null, clear the environment, and ensure regular immutable input trees.
    No fallback is provided. CUDA device IOCTLs are intentionally available only
    through the enumerated device files. File metadata is not hidden by ABI 1.
    """
    if platform.machine() != 'x86_64' or sys.platform != 'linux':
        raise RuntimeError('Only Linux x86-64 restriction ABI is implemented')
    if len(list(Path('/proc/self/task').iterdir())) != 1:
        raise RuntimeError('Restrictions must precede every worker thread')
    roots = [Path(p).resolve(strict=True) for p in (code, inputs, output)]
    if len(set(roots)) != 3 or any(a in b.parents for a in roots for b in roots):
        raise ValueError('Worker roots must be disjoint')
    runtime_roots = sorted({Path(p).resolve() for p in ('/usr', '/lib', '/lib64', sys.prefix, sys.base_prefix)
                            if Path(p).exists()})
    if any(p == q or p in q.parents or q in p.parents for p in roots for q in runtime_roots):
        raise ValueError('Worker roots must be outside system/runtime allowlists')
    shared_paths = []
    for value in shared_read_files:
        path = Path(value)
        if (not path.is_absolute() or '..' in path.parts
                or any(p.is_symlink() for p in (path, *path.parents))):
            raise ValueError('Shared worker inputs cannot traverse links')
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('Shared worker input must be a regular file')
        if any(path == p or p in path.parents for p in [roots[2], *runtime_roots]):
            raise ValueError('Shared input overlaps writable or runtime paths')
        shared_paths.append(path)
    if gpu_minor is not None and (type(gpu_minor) is not int or not 0 <= gpu_minor < 4096):
        raise ValueError('One verified GPU device minor is required')
    if gpu_minor is not None and (not parent_network_namespace or os.readlink('/proc/self/ns/net') == parent_network_namespace):
        raise RuntimeError('GPU IPC requires a verified separate network namespace')
    libc = C.CDLL(None, use_errno=True)
    abi = _check(libc.syscall(444, 0, 0, 1), 'Landlock unavailable')
    if abi < 1: raise RuntimeError('Landlock ABI 1 or later required')
    handled = (1 << (15 if abi >= 3 else 14 if abi >= 2 else 13)) - 1
    ruleset = _Ruleset(handled)
    fd = _check(libc.syscall(444, C.byref(ruleset), C.sizeof(ruleset), 0), 'Create Landlock ruleset')
    read_file, read_dir = 4, 8
    readable = read_file | read_dir
    writable = readable | 2 | 16 | 32 | 128 | 256  # normal files/dirs only
    if abi >= 3: writable |= 1 << 14
    def allow(path, rights):
        path = Path(path).resolve(strict=True)
        if not path.is_dir(): rights &= ~read_dir
        handle = os.open(path, os.O_PATH | os.O_CLOEXEC)
        try:
            rule = _PathRule(rights, handle)
            _check(libc.syscall(445, fd, 1, C.byref(rule), 0), 'Add Landlock path: ' + str(path))
        finally: os.close(handle)
    devices = []
    try:
        for path in [*runtime_roots, *roots[:2]]: allow(path, readable)
        for path in shared_paths: allow(path, read_file)
        allow(roots[2], writable)
        for name in ('/etc/ld.so.cache', '/proc/cpuinfo', '/proc/meminfo', '/proc/self', '/proc/sys/vm/mmap_min_addr',
                     '/sys/devices/system/cpu', '/sys/devices/system/node'):
            if Path(name).exists(): allow(name, readable)
        for name in ('/dev/null', '/dev/zero', '/dev/random', '/dev/urandom'):
            allow(name, read_file | (2 if name == '/dev/null' else 0))
        if gpu_minor is not None:
            devices = [f'/dev/nvidia{gpu_minor}', '/dev/nvidiactl', '/dev/nvidia-uvm']
            for name in devices:
                if not stat.S_ISCHR(Path(name).stat().st_mode): raise ValueError('GPU path is not a character device')
                allow(name, read_file | 2)
            for name in ('/proc/driver/nvidia', '/sys/bus/pci/devices'):
                if Path(name).exists(): allow(name, readable)
            for name in ('/proc/devices', '/sys/devices/system/memory/block_size_bytes'):
                allow(name, read_file)
            for info in Path('/proc/driver/nvidia/gpus').glob('*/information'):
                if re.search(r'^Device Minor:\s*'+str(gpu_minor)+r'\s*$', info.read_text(), re.MULTILINE):
                    # PCI entries are symlinks; bind the selected GPU's actual
                    # subtree, not every device in the host's /sys/devices.
                    allow(Path('/sys/bus/pci/devices')/info.parent.name, readable)
            # CUDA names newly created helper threads through /proc/.../comm.
            # This grants access only to this process's kernel thread records;
            # symlink targets still require their own Landlock authorization.
            # No other process, filesystem creation or persistent file root is
            # writable through this rule. Namespace/exec/ptrace stay denied.
            allow('/proc/self/task', readable | 2 | ((1 << 14) if abi >= 3 else 0))
        _check(libc.prctl(38, 1, 0, 0, 0), 'Set no_new_privs')
        _check(libc.prctl(4, 0, 0, 0, 0), 'Disable dumpability')
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        # Drop effective/permitted/inheritable capabilities. No exec or capset
        # is admitted by the subsequently installed default-deny filter.
        class Header(C.Structure): _fields_ = [('version', C.c_uint32), ('pid', C.c_int)]
        class Caps(C.Structure): _fields_ = [('effective', C.c_uint32), ('permitted', C.c_uint32), ('inheritable', C.c_uint32)]
        header = Header(0x20080522, 0)
        caps = (Caps * 2)()
        _check(libc.capset(C.byref(header), C.byref(caps)), 'Drop worker capabilities')
        _check(libc.syscall(446, fd, 0), 'Enforce Landlock')
    finally: os.close(fd)
    _seccomp(gpu_minor is not None)
    return {'backend': 'landlock_seccomp_v1', 'landlock_abi': abi, 'syscalls': 'default_deny',
            'network': 'private_namespace_unix_seqpacket_listener_no_outbound_connections' if gpu_minor is not None else 'connections_denied',
            'host_pid_namespace': True,
            'filesystem_namespace': False, 'file_metadata_hidden': False,
            'runtime': 'cuda' if gpu_minor is not None else 'cpu', 'gpu_devices': devices,
            'shared_read_file_count': len(shared_paths),
            'own_thread_proc_records_writable': gpu_minor is not None,
            'scope': 'reviewed_worker_and_pure_feature_grammar_only'}
