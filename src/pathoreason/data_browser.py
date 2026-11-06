"""Bounded, read-only pathology previews and explicit project-owned snapshots."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from .persistence import now
from .settings import ROOT

BASE = 'http://ai.gzfxyl.cn/api/v1/pathology'
MAX_BYTES = 2 * 1024 * 1024
DISEASE = ['DiseaseId', 'DiseaseCode', 'DiseaseName', 'DiagnosisStatus']
LABELS = dict(zip(
    'DiseaseId DiseaseCode DiseaseNameZh Organ OrganSystem Description Province City PatientCount HospitalId HospitalName SpecimenCount SlideCount PatientId Sex Age PatientDiseaseId DiagnosisDate DiagnosisStatus IsCurrent IsPrimary Note SpecimenId SpecimenNo SpecimenType AnatomicalSite CollectionDate SlideId SlideNo StainType WsiId FilePath FeaturePath ScanName SubtypeCode SubtypeNameZh SubtypeCategory AttributeCode AttributeNameZh OptionCode OptionNameZh NumericValue TextValue RecordDate Source ReportNo TestMethod ReportDate BiomarkerName BiomarkerType QualitativeResult QuantitativeValue QuantitativeUnit Interpretation RawResultText ReportId RawMention NormalizedMention MatchMethod Confidence NegationStatus VerificationStatus'.split(),
    '病种ID 病种编码 病种名称 器官 器官系统 描述 省份 城市 患者数 医院ID 医院名称 标本数 切片数 患者ID 性别 年龄 诊断记录ID 诊断日期 诊断状态 当前诊断 主要记录 备注 标本ID 标本编号 标本类型 取材部位 采集日期 切片ID 切片编号 染色 WSI标识 图像路径 特征路径 扫描文件名 亚型编码 亚型名称 亚型分类 属性编码 属性名称 选项编码 选项名称 数值 文本值 记录日期 来源 报告编号 检测方法 报告日期 标志物 标志物类型 定性结果 定量结果 定量单位 结果解读 原始结果 报告ID 原始命中 归一化命中 匹配方法 匹配置信度 否定状态 核验状态'.split()))


class Endpoint(BaseModel):
    path: str
    title: str
    group: str
    filters: list[str]
    fields: list[str]
    columns: list[str]
    paginated: bool = True
    note: str


def endpoint(path, title, group, filters, fields, columns, note, paginated=True):
    return Endpoint(path=path, title=title, group=group, filters=filters, fields=fields.split(), columns=columns.split(), note=note, paginated=paginated)


ENDPOINTS = [
    endpoint('/diseases', '疾病字典', '病种与概况', ['Keyword'], 'DiseaseId DiseaseCode DiseaseNameZh Organ OrganSystem Description', 'DiseaseNameZh DiseaseCode Organ OrganSystem', '按名称或编码查找，选定准确病种后查询明细。'),
    endpoint('/diseases/patient-count-by-province', '地域患者统计', '病种与概况', DISEASE + ['CurrentOnly'], 'Province City PatientCount', 'Province City PatientCount', '默认确诊、当前诊断；不分页。省市分组患者数不可直接当成全国去重人数。', False),
    endpoint('/diseases/sample-count-by-hospital', '医院样本统计', '病种与概况', DISEASE + ['CurrentOnly'], 'HospitalId HospitalName Province City PatientCount SpecimenCount SlideCount', 'HospitalName Province PatientCount SpecimenCount SlideCount', '默认确诊、当前诊断；不分页。跨院患者数不默认可加总。', False),
    endpoint('/diseases/patients', '患者', '患者与样本', DISEASE, 'PatientId Sex Age HospitalId PatientDiseaseId DiagnosisDate DiagnosisStatus IsCurrent IsPrimary Note', 'PatientId Sex Age HospitalId DiagnosisStatus', '一位患者可能有多条诊断记录，记录数不等于患者数。'),
    endpoint('/diseases/specimens', '标本', '患者与样本', DISEASE, 'PatientId DiseaseNameZh SpecimenId SpecimenNo SpecimenType Organ AnatomicalSite CollectionDate IsPrimary Note', 'SpecimenNo PatientId SpecimenType Organ AnatomicalSite', '关联切片或检测时同时使用患者与标本编号。'),
    endpoint('/diseases/slides', '切片', '患者与样本', DISEASE + ['StainType'], 'PatientId DiseaseNameZh SpecimenNo Organ SlideId SlideNo StainType WsiId FilePath FeaturePath ScanName', 'SlideNo PatientId SpecimenNo StainType FilePath FeaturePath', '路径可能为空；存在引用不等于文件可读。此接口不提供坐标或 attention。'),
    endpoint('/patients/disease-subtypes', '疾病亚型', '标签与检测', ['PatientId'], 'PatientId DiseaseNameZh SubtypeCode SubtypeNameZh SubtypeCategory IsPrimary Note', 'PatientId DiseaseNameZh SubtypeNameZh SubtypeCategory', '须指定患者；可能包含其他病种，亚型可重叠。'),
    endpoint('/patients/disease-attributes', '疾病属性', '标签与检测', ['PatientId'], 'PatientId DiseaseNameZh AttributeCode AttributeNameZh OptionCode OptionNameZh NumericValue TextValue RecordDate Source Note', 'PatientId DiseaseNameZh AttributeNameZh OptionNameZh NumericValue', '须指定患者；按目标病种过滤，保留单位、缺失与冲突。'),
    endpoint('/molecular-results', 'IHC / 分子结果', '标签与检测', ['PatientId', 'BiomarkerName'], 'PatientId SpecimenNo ReportNo TestMethod ReportDate BiomarkerName BiomarkerType QualitativeResult QuantitativeValue QuantitativeUnit Interpretation RawResultText', 'PatientId SpecimenNo BiomarkerName QualitativeResult QuantitativeValue QuantitativeUnit', '须指定患者；定性结果不能自动转为连续数值，标签不能直接赋给该患者全部切片。'),
    endpoint('/text-disease-matches', '文本命中追溯', '来源追溯', ['PatientId', 'DiseaseCode'], 'PatientId ReportId DiseaseCode DiseaseNameZh RawMention NormalizedMention MatchMethod Confidence NegationStatus VerificationStatus', 'PatientId DiseaseNameZh MatchMethod Confidence NegationStatus VerificationStatus', '指定患者或病种编码。Confidence 是文本匹配置信度，不是肿瘤概率。'),
]
BY_PATH = {e.path: e for e in ENDPOINTS}


class PreviewQuery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    endpoint: str
    params: dict[str, str | int | bool] = Field(default_factory=dict)
    page: int = Field(default=1, ge=1, le=10000, strict=True)
    page_size: int = Field(default=20, ge=1, le=100, strict=True)

    @model_validator(mode='after')
    def validate_scope(self):
        spec = BY_PATH.get(self.endpoint)
        if not spec or set(self.params) - set(spec.filters):
            raise ValueError('unsupported_endpoint_or_parameters')
        if any(len(str(v)) > 200 for v in self.params.values()):
            raise ValueError('query_value_too_long')
        if self.endpoint.startswith('/diseases/') and not any(str(self.params.get(k, '')).strip() for k in DISEASE[:3]):
            raise ValueError('disease_scope_required')
        if self.endpoint in {'/patients/disease-subtypes', '/patients/disease-attributes', '/molecular-results'} and not str(self.params.get('PatientId', '')).strip():
            raise ValueError('patient_scope_required')
        if self.endpoint == '/text-disease-matches' and not any(str(self.params.get(k, '')).strip() for k in ('PatientId', 'DiseaseCode')):
            raise ValueError('text_scope_required')
        if not spec.paginated and self.page != 1:
            raise ValueError('aggregate_is_unpaged')
        if 'CurrentOnly' in self.params and self.params['CurrentOnly'] not in (True, False, 'true', 'false'):
            raise ValueError('invalid_current_only')
        return self


class FigureMatch(BaseModel):
    title: str
    state: str
    reason: str
    next_step: str


class QueryPreview(BaseModel):
    query_id: str
    query: PreviewQuery
    title: str
    queried_at: str
    rows: list[dict[str, Any]]
    fields: list[str]
    row_count: int
    has_more: bool
    scope: str
    nonempty: dict[str, int]
    response_sha256: str
    figures: list[FigureMatch]


class QuerySummary(BaseModel):
    query_id: str
    title: str
    queried_at: str
    row_count: int
    page: int


class BrowserCatalog(BaseModel):
    endpoints: list[Endpoint]
    labels: dict[str, str]
    credential_configured: bool
    available: bool
    preview_limit: int = 100


class SnapshotInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_id: str = Field(pattern=r'^prj_[A-Za-z0-9_-]+$')
    query_id: str = Field(pattern=r'^dq_[0-9a-f]{32}$')


class SnapshotResult(BaseModel):
    project_id: str
    query_id: str
    relative_path: str
    draft: str


class DataBrowserError(Exception):
    def __init__(self, code, status=502):
        self.code, self.status = code, status


def credential_key():
    key = os.environ.get('PATHOREASON_DATA_API_KEY')
    if key:
        return key.strip()
    p = ROOT / '接口文档2.0.md'
    try:
        if p.is_symlink() or p.stat().st_mode & 0o077:
            return None
        match = re.search(r'X-AiData-Key:\s*([0-9a-fA-F-]{36})', p.read_text())
        return match.group(1) if match else None
    except OSError:
        return None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def transport(endpoint_path, params, key):
    request = urllib.request.Request(BASE + endpoint_path + '?' + urllib.parse.urlencode(params), headers={'Accept': 'application/json', 'X-AiData-Key': key})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=12) as response:
            raw = response.read(MAX_BYTES + 1)
    except Exception:
        raise DataBrowserError('data_upstream_unavailable') from None
    if len(raw) > MAX_BYTES:
        raise DataBrowserError('data_response_too_large')
    return raw


def figure_matches(endpoint_path, count, nonempty):
    slides = endpoint_path == '/diseases/slides'
    pixels = nonempty.get('FilePath', 0)
    return [
        FigureMatch(title='队列与标签分布', state='pending' if count else 'not_checked', reason='当前返回记录需按患者、标本与病种整理口径；分页样本不能代表完整队列。' if count else '当前没有记录，不能生成分布结论。', next_step='准备完整查询与去重规则；论文资产适配需另行核验。'),
        FigureMatch(title='真实组织概览 / ROI', state='pending' if slides else 'not_checked', reason=(f'当前 {count} 条记录中 {pixels} 条有图像路径，文件尚未核验。' if pixels else '当前切片样本未提供图像路径。') if slides and count else '需要查询切片并核验真实图像来源。', next_step='核对 FilePath 和实际解码环境；ROI 另需选区与空间映射。'),
        FigureMatch(title='Attention 热点图 / Top patches', state='pending', reason='已有空间渲染器；接口不提供坐标和模型归因，尚不能生成热点图。', next_step='补齐像素、真实坐标、特征行序、checkpoint 与归因回执。'),
        FigureMatch(title='ROC / PR、混淆矩阵与回归图', state='not_checked', reason='需要真实实验预测及真值；本次接口预览未检查实验输出。', next_step='在研究对话中关联对应实验、划分和评价规则。'),
        FigureMatch(title='生存、校准与决策曲线', state='pending', reason='公开接口未定义完整随访契约，对应临床图件提供器尚未注册。', next_step='补充随访/事件数据并实现对应统计适配。'),
        FigureMatch(title='概念示意图', state='not_checked', reason='可走现有 Seedream 路线；此预览不触发生图，也不提供患者素材。', next_step='在研究对话中明确概念图内容与执行范围。'),
    ]


class DataBrowser:
    def __init__(self, service):
        self.s = service
        self.cache = OrderedDict()
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(3)

    def catalog(self):
        return BrowserCatalog(endpoints=ENDPOINTS, labels=LABELS, credential_configured=bool(credential_key()), available=self.s.config.get('execution_environment', 'bxn-server') == 'bxn-server')

    def _prune(self):
        for key in list(self.cache):
            if time.monotonic() - self.cache[key][0] > 1800:
                del self.cache[key]
        while len(self.cache) > 16:
            self.cache.popitem(last=False)

    def get(self, query_id):
        with self.lock:
            self._prune()
            item = self.cache.get(query_id)
            if not item:
                raise DataBrowserError('data_preview_expired', 410)
            return item[1], item[2]

    def recent(self):
        with self.lock:
            self._prune()
            return [QuerySummary(query_id=p.query_id, title=p.title, queried_at=p.queried_at, row_count=p.row_count, page=p.query.page) for _, p, _ in reversed(self.cache.values())]

    def snapshot_root(self, project_id):
        if not re.fullmatch(r'prj_[A-Za-z0-9_-]+', project_id):
            raise DataBrowserError('data_snapshot_path_invalid', 422)
        self.s.store.project(project_id)
        path = self.s.data / 'projects' / project_id / 'inputs/data-browser'
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise DataBrowserError('data_snapshot_path_invalid', 409)
        return path

    def snapshots(self, project_id):
        root = self.snapshot_root(project_id)
        if not root.exists():
            return []
        results = []
        from itertools import islice
        for p in islice(root.iterdir(), 500):
            if not re.fullmatch(r'dq_[0-9a-f]{32}', p.name) or p.is_symlink():
                continue
            try:
                file = p / 'receipt.json'
                if file.is_symlink() or file.stat().st_size > 65536:
                    continue
                r = json.loads(file.read_text())
                if r['project_id'] != project_id or r['query_id'] != p.name:
                    continue
                results.append(QuerySummary(query_id=p.name, title=BY_PATH[r['query']['endpoint']].title, queried_at=r['queried_at'], row_count=r['row_count'], page=r['query']['page']))
            except (OSError, ValueError, KeyError):
                continue
        return sorted(results, key=lambda q: q.queried_at, reverse=True)[:50]

    def load_snapshot(self, project_id, query_id):
        if not re.fullmatch(r'dq_[0-9a-f]{32}', query_id):
            raise DataBrowserError('data_snapshot_path_invalid', 422)
        path = self.snapshot_root(project_id) / query_id
        try:
            if path.is_symlink():
                raise ValueError()
            files = {}
            for name, cap in [('receipt.json', 65536), ('response.json', MAX_BYTES), ('preview.json', MAX_BYTES * 6)]:
                p = path / name
                if p.is_symlink() or p.stat().st_size > cap:
                    raise ValueError()
                files[name] = p.read_bytes()
            receipt = json.loads(files['receipt.json'])
            if receipt['project_id'] != project_id or receipt['query_id'] != query_id:
                raise ValueError()
            for name in ('response.json', 'preview.json'):
                if hashlib.sha256(files[name]).hexdigest() != receipt['sha256'][name]:
                    raise ValueError()
            preview = QueryPreview.model_validate_json(files['preview.json'])
            if preview.query_id != query_id or preview.response_sha256 != receipt['sha256']['response.json']:
                raise ValueError()
        except (OSError, ValueError, KeyError):
            raise DataBrowserError('data_snapshot_changed', 409) from None
        with self.lock:
            self.cache[query_id] = (time.monotonic(), preview, files['response.json'])
            self._prune()
        return preview

    def query(self, query):
        if not self.catalog().available:
            raise DataBrowserError('data_server_only', 503)
        key = credential_key()
        if not key:
            raise DataBrowserError('data_credential_missing', 503)
        if not self.slots.acquire(blocking=False):
            raise DataBrowserError('data_query_busy', 429)
        try:
            spec = BY_PATH[query.endpoint]
            params = dict(query.params)
            if 'DiagnosisStatus' in spec.filters:
                params.setdefault('DiagnosisStatus', '确诊')
            if 'CurrentOnly' in spec.filters:
                params.setdefault('CurrentOnly', True)
            query = query.model_copy(update={'params': params})
            actual = {k: str(v).lower() if type(v) is bool else v for k, v in params.items()}
            if spec.paginated:
                actual.update(PageIndex=query.page, PageSize=query.page_size)
            raw = transport(query.endpoint, actual, key)
            try:
                body = json.loads(raw)
                rows = body['data']
                if str(body['code']) != '200' or not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
                    raise ValueError()
                if len(rows) > (query.page_size if spec.paginated else 5000):
                    raise ValueError()
            except (ValueError, KeyError, TypeError):
                raise DataBrowserError('data_response_invalid') from None
            fields = list(dict.fromkeys(spec.fields + [k for row in rows for k in row]))
            nonempty = {k: sum(r.get(k) is not None and r.get(k) != '' for r in rows) for k in fields}
            preview = QueryPreview(query_id='dq_' + uuid.uuid4().hex, query=query, title=spec.title, queried_at=now(), rows=rows, fields=fields, row_count=len(rows), has_more=spec.paginated and len(rows) == query.page_size, scope='当前页样本' if spec.paginated else '当前条件的接口聚合', nonempty=nonempty, response_sha256=hashlib.sha256(raw).hexdigest(), figures=figure_matches(query.endpoint, len(rows), nonempty))
            with self.lock:
                self.cache[preview.query_id] = (time.monotonic(), preview, raw)
                self._prune()
            return preview
        finally:
            self.slots.release()

    def save(self, body):
        preview, raw = self.get(body.query_id)
        relative = f'inputs/data-browser/{body.query_id}'
        # Hold the project lifecycle write lock while creating its owned snapshot.
        with self.s.store.connect(True) as db:
            self.s.store.check_project(db, body.project_id, writable=True)
            root = self.s.data / 'projects' / body.project_id
            target = root / relative
            if any(p.is_symlink() for p in (target, *target.parents)):
                raise DataBrowserError('data_snapshot_path_invalid', 409)
            payloads = {'response.json': raw, 'preview.json': (preview.model_dump_json(indent=2) + '\n').encode()}
            receipt = {'schema_version': 'pathoreason.data-preview/1', 'query_id': preview.query_id, 'project_id': body.project_id, 'query': preview.query.model_dump(), 'queried_at': preview.queried_at, 'row_count': preview.row_count, 'scope': preview.scope, 'complete_dataset': False, 'sha256': {k: hashlib.sha256(v).hexdigest() for k, v in payloads.items()}}
            payloads['receipt.json'] = (json.dumps(receipt, ensure_ascii=False, indent=2) + '\n').encode()
            if target.exists():
                if any((target / name).is_symlink() or not (target / name).is_file() or (target / name).read_bytes() != value for name, value in payloads.items()):
                    raise DataBrowserError('data_snapshot_changed', 409)
            else:
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                staging = target.with_name('.' + target.name + '-' + uuid.uuid4().hex)
                staging.mkdir(mode=0o700)
                try:
                    for name, value in payloads.items():
                        with (staging / name).open('xb') as file:
                            file.write(value)
                    staging.rename(target)
                finally:
                    if staging.exists():
                        shutil.rmtree(staging)
        draft = (f'请基于已保存的数据查询快照分析数据适用性与图表缺口。\n'
                 f'查询：{preview.title}；{preview.scope}，{preview.row_count} 条，第 {preview.query.page} 页；时间：{preview.queried_at}。\n'
                 f'项目输入：{relative}/receipt.json；原始响应：{relative}/response.json；字段与缺口：{relative}/preview.json。\n'
                 '这是查询预览，不代表完整队列或文件已可读。请读取回执中的准确过滤条件，保留原始数据。')
        return SnapshotResult(project_id=body.project_id, query_id=body.query_id, relative_path=relative, draft=draft)
