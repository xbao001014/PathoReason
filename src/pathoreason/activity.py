"""Public execution metadata; never infer a rationale or copy raw tool payloads."""
import math

LABELS = {
    'bash': '执行命令', 'read': '读取文件', 'write': '写入文件',
    'edit': '编辑文件', 'apply_patch': '修改文件', 'glob': '查找文件',
    'grep': '检索文件内容', 'list': '列出目录', 'webfetch': '读取网页',
    'websearch': '搜索网页', 'skill': '加载 Skill', 'task': '调用子任务',
    'todowrite': '更新任务清单', 'todoread': '读取任务清单',
    'pathoreason_research': '调用研究工具', 'pathoreason_dialogue_offer': '提供下一步选择',
}


def tool_summary(part):
    state = part.get('state') or {}
    name = part.get('tool', 'tool')
    summary = LABELS.get(name, '调用工具')
    if name == 'skill':
        from .formal import TITLES
        titles = {**TITLES, 'results-explanation': '结果解读',
                  'pathology-data-api': '病理接口数据接入',
                  'benchmark-design': 'Benchmark 选型与比较方案'}
        inputs = state.get('input') or {}
        skill = inputs.get('name') if isinstance(inputs, dict) else None
        if isinstance(skill, str) and skill in titles:
            summary = '加载「' + titles[skill] + '」Skill'
    duration = None
    timing = state.get('time') or {}
    start, end = timing.get('start'), timing.get('end')
    if all(type(t) in (int, float) and math.isfinite(t) for t in (start, end)) and 0 <= start <= end:
        duration = int(end - start)
    return {'id': part['id'], 'name': name, 'status': state.get('status', 'unknown'),
            'summary': summary, 'duration_ms': duration}


def activity_phase(messages):
    if not messages:
        return 'waiting'
    parts = messages[-1].get('parts', [])
    if any(p.get('type') == 'tool' and (p.get('state') or {}).get('status') in ('pending', 'running') for p in parts):
        return 'tool'
    for part in reversed(parts):
        if part.get('type') == 'text' and part.get('text', '').strip():
            return 'responding'
        if part.get('type') == 'reasoning':
            return 'thinking'
        if part.get('type') == 'tool':
            return 'waiting'
    return 'waiting'
