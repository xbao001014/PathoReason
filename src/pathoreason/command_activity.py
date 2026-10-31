"""Conservative shell structure labels. No raw command, model title, path, or output export."""
import ast
import hashlib
import re
import shlex
from pathlib import PurePosixPath

LABELS={'read':'读取文件','search':'检索文件内容','logs':'查看运行日志','status':'检查进程或设备','wait':'等待任务状态',
        'dependencies':'安装或检查依赖','prepare':'准备数据文件','config':'生成配置文件','train':'运行训练入口',
        'publish':'登记研究成果','python':'运行 Python 脚本','script':'运行脚本','files':'整理工作目录','command':'执行命令'}
REPEAT={'read','search','logs','status','wait'}


def python_kind(code):
    try:tree=ast.parse(code)
    except (SyntaxError,ValueError,RecursionError):return 'python'
    calls=[n.func for n in ast.walk(tree) if isinstance(n,ast.Call)]
    attrs={n.attr for n in calls if isinstance(n,ast.Attribute)}
    if attrs & {'create_dataset','to_csv','savez','savez_compressed'}:return 'prepare'
    if attrs & {'safe_dump'}:return 'config'
    return 'python'


def command_activity(command):
    if not isinstance(command,str) or len(command)>65536:return {'kind':'command','summary':LABELS['command'],'repeat_key':None}
    # Heredoc content is code/data, never a shell instruction. Only parse Python bodies as AST.
    bodies=[]
    shell=re.sub(r"([^\n]*?)<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2[^\n]*\n([\s\S]*?)\n\3(?:\n|$)",lambda m: _heredoc(m,bodies),command)
    try:
        lexer=shlex.shlex(shell,posix=True,punctuation_chars=';&|()<>\n');lexer.whitespace=' \t\r';lexer.whitespace_split=True;lexer.commenters='#'
        parts=[[]]
        for token in lexer:
            if token and all(c in ';&|()\n' for c in token):parts.append([])
            else:parts[-1].append(token)
    except ValueError:return {'kind':'command','summary':LABELS['command'],'repeat_key':None}
    kinds=[]
    def add(kind):
        if kind and kind not in kinds:kinds.append(kind)
    variables={}
    for segment in parts:
        while segment and re.match(r'^[A-Za-z_][A-Za-z0-9_]*=',segment[0]):
            key,value=segment[0].split('=',1)
            if '$' not in value and '`' not in value:variables[key]=value
            segment=segment[1:]
        segment=[variables.get(x[1:],x) if re.fullmatch(r'\$[A-Za-z_][A-Za-z0-9_]*',x) else x for x in segment]
        if not segment:continue
        binary=PurePosixPath(segment[0]).name;args=segment[1:]
        if binary in ('cd','echo','printf','true'):continue
        if binary in ('cat','sed','head'):add('read')
        elif binary=='tail':add('logs')
        elif binary in ('grep','rg','find'):add('search')
        elif binary in ('ps','pgrep','nvidia-smi','stat'):add('status')
        elif binary in ('sleep','wait'):add('wait')
        elif binary in ('pip','pip3','uv') and any(x in args for x in ('install','sync','freeze','show')):add('dependencies')
        elif binary in ('mkdir','cp','mv','ls'):add('files')
        elif binary in ('python','python3') or re.fullmatch(r'python3\.\d+',binary):
            if args[:2]==['-m','pip']:add('dependencies');continue
            names={PurePosixPath(x).name for x in args if not x.startswith('-')}
            if 'study_io.py' in names and 'publish' in args:add('publish')
            elif names & {'train.py','train_mil.py','run_holdout.py','run_cv.py'} or 'run-holdout' in args or 'run-cv' in args:add('train')
            elif any(x.endswith('.py') for x in names):add('script')
            elif '-c' in args:
                i=args.index('-c');add(python_kind(args[i+1]) if i+1<len(args) else 'python')
            elif not bodies:add('python')
        else:add('command')
    for header,body in bodies:
        if re.search(r'\bpython(?:3(?:\.\d+)?)?\s',header):add(python_kind(body))
        else:add('command')
    # Helpers/variable-based invocations are unknown: do not guess from prose or paths in their bodies.
    order=['read','search','files','dependencies','prepare','config','python','script','train','publish','logs','status','wait','command']
    kinds=sorted(kinds,key=order.index) or ['command']
    kind=kinds[0] if len(kinds)==1 else 'compound'
    summary=' · '.join(LABELS[k] for k in kinds[:3])+('等操作' if len(kinds)>3 else '')
    repeat=hashlib.sha256(command.encode()).hexdigest() if kind in REPEAT else None
    return {'kind':kind,'summary':summary,'repeat_key':repeat}


def _heredoc(match,bodies):
    bodies.append((match[1],match[4]))
    return match[1]+' -\n'
