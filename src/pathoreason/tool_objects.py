"""Bounded object references from structured tool inputs; never export payloads or execute code."""
import ast
import re
import shlex
from pathlib import PurePosixPath
from urllib.parse import urlsplit, urlunsplit

MAX_TARGETS = 12
TRAINING_OPERATIONS = {'list': '列出训练实验', 'inspect': '检查训练实验', 'environment': '检查训练环境',
                       'prepare': '准备训练实验', 'launch': '启动训练实验', 'stop': '停止训练实验', 'retry': '重试训练实验'}


def safe_path(value):
    if not isinstance(value, str) or not value or len(value) > 1024:
        return None
    # Reject shell expressions, controls and argument-like strings instead of displaying them as a file.
    if value != value.strip() or value.startswith('-') or re.search(r'[\x00-\x1f\x7f\u202a-\u202e\u2066-\u2069$`<>|;?*=]', value) or '://' in value:
        return None
    return value


def python_objects(code):
    """Recognize only literal top-level file operations, without evaluating arbitrary Python."""
    try:
        tree = ast.parse(code)
        if sum(1 for _ in ast.walk(tree)) > 4096:
            return []
    except (SyntaxError, ValueError, RecursionError):
        return []
    names, found = {}, []

    def value(node, depth=0):
        if depth > 32:
            return None
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return names.get(node.id)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            left, right = value(node.left, depth+1), value(node.right, depth+1)
            return str(PurePosixPath(left) / right) if left is not None and right is not None else None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'Path' and len(node.args) == 1:
            return value(node.args[0], depth+1)
        return None

    def call(node):
        if not isinstance(node, ast.Call):
            return
        if isinstance(node.func, ast.Attribute) and node.func.attr in {'write_text', 'write_bytes', 'read_text', 'read_bytes', 'open'}:
            path = value(node.func.value)
            action = 'write' if node.func.attr.startswith('write') else 'read'
            if node.func.attr == 'open':
                mode = value(node.args[0]) if node.args else 'r'
                for item in node.keywords:
                    if item.arg == 'mode':
                        mode = value(item.value)
                action = None if mode is None else 'write' if any(c in mode for c in 'wax+') else 'read'
            found.append(('file', path, action))
        elif isinstance(node.func, ast.Name) and node.func.id == 'open' and node.args:
            mode = value(node.args[1]) if len(node.args) > 1 else 'r'
            for item in node.keywords:
                if item.arg == 'mode':
                    mode = value(item.value)
            found.append(('file', value(node.args[0]), None if mode is None else 'write' if any(c in mode for c in 'wax+') else 'read'))

    def statements(body):
        for node in body:
            if isinstance(node, ast.Assign):
                call(node.value)
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names[target.id] = value(node.value)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                call(node.value)
                names[node.target.id] = value(node.value)
            elif isinstance(node, ast.Expr):
                call(node.value)
            elif isinstance(node, ast.With):
                for item in node.items:
                    call(item.context_expr)
                statements(node.body)
            # Branches/functions/loops may never execute; do not invent their affected files.
    statements(tree.body)
    return found


def command_objects(command):
    if not isinstance(command, str) or len(command) > 65536:
        return []
    found = []
    def heredoc(match):
        if re.search(r'\bpython(?:3(?:\.\d+)?)?\s', match[1]):
            found.extend(python_objects(match[4]))
        return match[1] + ' -\n'
    shell = re.sub(r"([^\n]*?)<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2[^\n]*\n([\s\S]*?)\n\3(?:\n|$)", heredoc, command)
    try:
        lexer = shlex.shlex(shell, posix=True, punctuation_chars=';&|()<>\n')
        lexer.whitespace = ' \t\r'; lexer.whitespace_split = True; lexer.commenters = '#'
        segments = [[]]
        for token in lexer:
            if token and all(c in ';&|()\n' for c in token):
                segments.append([])
            else:
                segments[-1].append(token)
    except ValueError:
        return []
    for tokens in segments:
        if not tokens:
            continue
        # Substitution/variable commands cannot identify a concrete executable or target reliably.
        if any('$' in t or '`' in t for t in tokens):
            continue
        binary, args = PurePosixPath(tokens[0]).name, tokens[1:]
        for index, item in enumerate(args[:-1]):
            if item in ('>', '>>'):
                found.append(('file', args[index+1], 'write'))
            elif item == '<':
                found.append(('file', args[index+1], 'read'))
        args = args[:next((i for i, x in enumerate(args) if x in ('>', '>>', '<', '2>', '2>>')), len(args))]
        if re.fullmatch(r'python(?:3(?:\.\d+)?)?', binary):
            if args[:1] == ['-c'] and len(args) > 1:
                found.extend(python_objects(args[1]))
            elif args and not args[0].startswith('-') and args[0].endswith('.py'):
                found.append(('script', args[0], 'run'))
                # Path arguments are admitted only when their flag explicitly identifies a file.
                for i, arg in enumerate(args[:-1]):
                    if arg in ('--file', '--config', '--yaml_path', '--plan', '--plan-path', '--input', '--output'):
                        found.append(('file', args[i+1], 'write' if arg == '--output' else 'read'))
        elif binary in ('bash', 'sh', 'node') and args and not args[0].startswith('-'):
            found.append(('script', args[0], 'run'))
        elif binary in ('cat', 'head', 'tail', 'ls', 'stat', 'tee'):
            skip = False
            for arg in args:
                if skip:
                    skip = False; continue
                if arg in ('-n', '-c', '--lines', '--bytes'):
                    skip = True; continue
                if not arg.startswith('-') and not arg.isdigit():
                    found.append(('directory' if binary == 'ls' else 'file', arg, 'write' if binary == 'tee' else 'read'))
    return found


def tool_objects(name, inputs):
    if not isinstance(inputs, dict):
        return {'targets': [], 'target_count': 0, 'operation': None, 'working_directory': None}
    found, operation = [], None
    if name in ('read', 'write', 'edit'):
        found.append(('file', inputs.get('filePath') or inputs.get('path'), name))
    elif name == 'apply_patch':
        patch = inputs.get('patchText')
        if isinstance(patch, str) and len(patch) <= 1000000:
            for action, path in re.findall(r'^\*\*\* (Add File|Update File|Delete File|Move to): (.+)$', patch, re.M):
                found.append(('file', path, 'delete' if action == 'Delete File' else 'write' if action in ('Add File', 'Move to') else 'edit'))
    elif name in ('glob', 'grep', 'list'):
        pattern = inputs.get('pattern' if name == 'glob' else 'include') if name != 'list' else None
        if isinstance(pattern, str) and re.fullmatch(r'[\w/.*?\[\]{}!, -]{1,256}', pattern):
            found.append(('pattern', pattern, None))
        found.append(('directory', inputs.get('path'), 'read'))
    elif name == 'bash':
        found.extend(command_objects(inputs.get('command')))
    elif name == 'skill':
        skill = inputs.get('name')
        if isinstance(skill, str) and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,99}', skill):
            found.append(('skill', skill, None))
    elif name == 'webfetch':
        raw = inputs.get('url')
        if isinstance(raw, str) and len(raw) <= 4096:
            try:
                url = urlsplit(raw)
                if url.scheme in ('http', 'https') and url.hostname:
                    # Credentials, signed query strings and fragments are never public metadata.
                    host = url.hostname + (':'+str(url.port) if url.port else '')
                    label = urlunsplit((url.scheme, host, url.path, '', ''))
                    if not re.search(r'[\x00-\x1f\x7f]', label) and len(label) <= 1024:
                        found.append(('website', label, None))
            except ValueError:
                pass
    elif name == 'pathoreason_dialogue_training':
        raw = inputs.get('operation')
        if isinstance(raw, str) and raw in TRAINING_OPERATIONS:
            operation = raw
        experiment = inputs.get('experiment_id')
        if isinstance(experiment, str) and re.fullmatch(r'exp_[a-zA-Z0-9_-]{1,100}', experiment):
            found.append(('experiment', experiment, None))
        found.append(('file', inputs.get('plan_path'), 'read'))
    targets = []
    for kind, label, action in found:
        if kind not in ('website', 'skill', 'experiment', 'pattern'):
            label = safe_path(label)
        if label is not None:
            target = {'kind': kind, 'label': label, 'action': action}
            if target not in targets:
                targets.append(target)
    return {'targets': targets[:MAX_TARGETS], 'target_count': len(targets), 'operation': operation, 'working_directory': safe_path(inputs.get('workdir')) if name == 'bash' else None}
