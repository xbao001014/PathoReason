import {useEffect,useState} from 'react';
import type {ArtifactRecord,LegacyHistoryEntry} from './generated';
import {Info} from './BusinessPanel';
export async function resolveArtifact(pid:string,aid:string):Promise<ArtifactRecord>{
 const r=await fetch('/api/v2/research-projects/'+encodeURIComponent(pid)+'/artifacts/'+encodeURIComponent(aid));
 if(!r.ok)throw new Error(r.status===409?'引用存在多个来源，请从研究成果中选择。':'该引用不属于当前项目的已绑定成果。');
 return r.json();
}
export function Provenance({pid,aid}:{pid:string;aid:string}){
 const [record,setRecord]=useState<ArtifactRecord|null>(null),[error,setError]=useState('');
 useEffect(()=>{let live=true;setRecord(null);setError('');resolveArtifact(pid,aid).then(r=>{if(live)setRecord(r);}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[pid,aid]);
 const chain=record?[record.provenance.origin,...record.provenance.transfers??[]]:[];
 return <details className="provenance-details"><summary>成果来源</summary>{error?<p role="alert">{error}</p>:record?<><Info text="来源链核对身份与文件字节，不代表独立科学审核通过。交接来源由快照声明，未进行身份签名验证。"/><ol>{chain.map((h,i)=><li key={i}><strong>{i===0?'原始记录':'快照交接'} · {h.environment==='local'?'本机':h.environment==='bxn-server'?'服务器':'未知环境'}</strong><code>{h.project_id} / {h.artifact_id}</code></li>)}</ol><dl><dt>文件 SHA256</dt><dd><code>{record.identity.sha256}</code></dd><dt>来源身份</dt><dd><code>{'artifact_id' in record.source?record.source.artifact_id:record.source.reference.resource_id}</code></dd></dl></>:<p role="status">正在读取…</p>}</details>;
}
export function LegacyHistory({pid}:{pid:string}){
 const [rows,setRows]=useState<LegacyHistoryEntry[]>([]),[error,setError]=useState('');
 useEffect(()=>{let live=true;setRows([]);setError('');fetch('/api/v2/research-projects/'+encodeURIComponent(pid)+'/legacy-history').then(async r=>{if(!r.ok)throw new Error('历史记录暂时无法读取');return r.json();}).then(r=>{if(live)setRows(r);}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[pid]);
 if(!rows.length&&!error)return null;
 return <details className="legacy-history"><summary>历史审阅 <span>{rows.length}</span></summary><Info text="这些记录来自旧研究流程，仅供查看；不是当前 Agent 会话，不会重放操作。"/>{error&&<p role="alert">{error}</p>}{rows.map(r=><article key={r.id}><header><strong>{r.source_kind==='review'?'历史审阅':'历史修复'}</strong><time>{r.occurred_at?.replace('T',' ').slice(0,16)}</time></header><p>{r.question||'无附加意见'}</p>{r.answer&&<p>{r.answer}</p>}</article>)}</details>;
}
