# 分页 helper

plans/data-queries-v1.json 使用 UTF-8 JSON。例如先取疾病字典（实际病种由任务给出）：

```json
{
  "queries": [
    {"endpoint": "/diseases", "params": {"Keyword": "实际病种"}, "page_size": 1000, "max_pages": 10}
  ]
}
```

字典身份确认后，为主列表和患者富集生成另一份有界计划。每项 query 的 params 只含接口文档允许的过滤条件；分页由 helper 管理。两个聚合端点自动按非分页处理。患者富集必须显式 PatientId，避免意外查询所有患者。计划只留在项目内。

输出结构：

```text
inputs/source-vNEW/
  plan.json
  q00000/
    page-0001.request.json
    page-0001.response.json
    page-0001.receipt.json
    rows.json
    complete.json
  summary.json
```

每页响应 SHA 校验的是 response.json 原字节；rows.json 有自己的摘要。complete.json 只在全部页完成后写入；记录 query 的 SHA、分页文件及合并文件。命令 stdout 仅输出聚合计数与完成摘要路径，不输出患者记录或密钥。

凭据默认在进程内从服务器受控接口说明提取；也可设置 PATHOREASON_DATA_API_KEY 环境变量。不要在命令行传递密钥或将其写入计划。helper 不读取凭据到模型上下文。

相同计划与输出可再次执行：只跳过 SHA 校验通过的完整查询，继续未开始的查询。已开始但无 complete.json 的查询报 reconciliation_required；先核对各页回执与原生调用状态，不能删除标记强行续跑。更换过滤条件应使用新计划和新输出目录，不复用旧完成标记。

helper 不自动重试，不自动突破 max_pages，不调用训练或图像服务。它只证明请求及保存情况，不能替代关联、标签核验和科学判断。使用多患者批次时可在原生命令预算内设置合理超时，前端回合中断后先检查原进程和文件，再决定是否续接。
