# 病理接口 2.0（无凭据摘要）

来源：服务器操作者提供的 接口文档2.0.md，2026-10-31 核对。这里不复制密钥、患者记录或本次实验结果。若实际服务结构与本摘要不符，保存响应证据并核对更新后的文档，不猜造字段。

Base URL: http://ai.gzfxyl.cn/api/v1/pathology 。请求为 GET；认证头 X-AiData-Key，由 helper 在进程内读取。列表返回 code/data；code=200 且 data 为数组才按成功数据处理。

PageIndex 从 1 开始；PageSize 上限 1000，疾病字典默认 50、其他列表默认 100。两项统计接口不分页。未传 DiagnosisStatus 默认“确诊”，显式空值表示不按诊断状态过滤；不能默默改变人群定义。CurrentOnly 仅用于文档列明的统计接口，不假定患者列表支持该参数。

| 端点（相对 Base） | 查询条件 | 结果用途 |
|---|---|---|
| /diseases | Keyword + 分页 | DiseaseId、DiseaseCode、DiseaseNameZh、Organ、OrganSystem；模糊命中须确认精确病种 |
| /diseases/patient-count-by-province | DiseaseId / DiseaseCode / DiseaseName 三选一；DiagnosisStatus、CurrentOnly | 非分页，地域患者聚合 |
| /diseases/sample-count-by-hospital | 同上 | 非分页，PatientCount、SpecimenCount、SlideCount |
| /diseases/patients | 病种条件、DiagnosisStatus + 分页 | PatientId、PatientDiseaseId、HospitalId、人口学、诊断状态；行不是唯一患者 |
| /diseases/specimens | 病种条件、DiagnosisStatus + 分页 | PatientId、SpecimenId、SpecimenNo、取材部位、主标本标记 |
| /diseases/slides | 病种条件、DiagnosisStatus、StainType + 分页 | PatientId、SpecimenNo、SlideId、WsiId、FilePath、FeaturePath |
| /patients/disease-subtypes | PatientId + 分页 | DiseaseNameZh、SubtypeCode/Name/Category、IsPrimary、Note |
| /patients/disease-attributes | PatientId + 分页 | DiseaseNameZh、AttributeCode/Name、OptionCode/Name、NumericValue、TextValue、Source |
| /molecular-results | PatientId、BiomarkerName + 分页 | SpecimenNo、ReportNo、BiomarkerName、QualitativeResult、QuantitativeValue/Unit、RawResultText |
| /text-disease-matches | PatientId、DiseaseCode + 分页 | 报告命中、否定状态、匹配方法、核验状态；按用户任务范围决定是否需要 |

疾病亚型和属性接口不接收病种过滤条件；取得患者记录后还须按 DiseaseNameZh 过滤。分子结果应先映射到目标病种的 (PatientId, SpecimenNo) 集合，并报告未匹配项及关联冲突。多院数据应核验 ID 是否全局唯一，不默认标本号跨院唯一。

统计接口与列表可能有不同默认过滤，跨表数量差异需要解释，不为凑齐数量强制去重或删除记录。SubtypeCategory/Source 等来源标记是数据来源，不等于人工审核。危险度、Ki-67 等标签含单位和文本形式，具体任务标准化应由研究 Agent 根据证据建立规则。

FilePath / FeaturePath 指向已有存储位置，并非已下载文件。保留原路径并只读核验；创建项目自己的清单、派生数据和划分，不向旧实验可写目录输出。
