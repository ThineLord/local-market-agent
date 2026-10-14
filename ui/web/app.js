import {createBullScene} from './bull.js';

const $=s=>document.querySelector(s);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icons={
  overview:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  watchlist:'<path d="M3 16 8 11l4 3 8-9M15 5h5v5"/>',
  briefs:'<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6M9 16h3"/>',
  signals:'<path d="M3 12h4l3-7 4 14 3-7h4"/>',
  risk:'<path d="m12 3 8 3v6c0 5-8 9-8 9S4 17 4 12V6Z"/><path d="m8 12 3 3 5-6"/>',
  ledger:'<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 3v18M12 8h4M12 12h4M12 16h4"/>',
  audit:'<circle cx="5" cy="6" r="2"/><circle cx="19" cy="18" r="2"/><circle cx="5" cy="18" r="2"/><path d="M5 8v8M7 18h10M7 6h6a6 6 0 0 1 6 6v4"/>',
  performance:'<path d="M4 4v16h17M8 15v-4M13 15V7M18 15V4"/>',
  operations:'<path d="M3 7h18M3 17h18"/><circle cx="8" cy="7" r="3"/><circle cx="16" cy="17" r="3"/>',
  settings:'<circle cx="12" cy="12" r="3"/><path d="m9 3-1 3-3 1-2 5 2 5 3 1 1 3h6l1-3 3-1 2-5-2-5-3-1-1-3Z"/>',
  arrow:'<path d="M4 12h15m-5-5 5 5-5 5"/>',chevron:'<path d="m9 5 7 7-7 7"/>',left:'<path d="m15 5-7 7 7 7"/>',
  search:'<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',refresh:'<path d="M20 8a8 8 0 1 0 0 8M20 3v5h-5"/>',
  pause:'<path d="M9 5v14M15 5v14"/>',play:'<path d="m8 4 12 8-12 8Z"/>',close:'<path d="m6 6 12 12M6 18 18 6"/>',
  export:'<path d="M12 3v12m-4-4 4 4 4-4M4 15v5h16v-5"/>',menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',external:'<path d="M14 3h7v7M21 3 10 14M10 5H4v15h15v-6"/>'
};
const icon=name=>`<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${icons[name]||icons.briefs}</svg>`;
const names={overview:'Overview',watchlist:'Watchlist',briefs:'Market Brief',signals:'Signals',risk:'Risk Decisions',ledger:'Paper Ledger',audit:'Audit Chain',performance:'Performance Report',operations:'Phase 7 Operations',settings:'Settings'};
const groups=[['', ['overview']],['RESEARCH',['watchlist','briefs','signals']],['PORTFOLIO',['risk','ledger','audit','performance']],['WORKSPACE',['operations']]];
$('#navigation').innerHTML=groups.map(([label,pages])=>`${label?`<div class="nav-section">${label}</div>`:''}${pages.map(p=>`<a href="#${p}" class="nav-item" data-page="${p}">${icon(p)}<span>${names[p]}</span></a>`).join('')}`).join('');
document.querySelector('[data-icon="settings"]').innerHTML=icon('settings');
$('#refresh').innerHTML=icon('refresh');$('#motion-toggle').innerHTML=icon('pause');$('#menu-toggle').innerHTML=icon('menu');$('#close-detail').innerHTML=icon('close');
const scene=createBullScene($('#bull-scene'));
let state={page:'overview',tab:'',search:'',filter:'',pageIndex:0,brief:0,report:0,sort:null,direction:1};
let data=null,activeTable=null,details=[],currentDetail=null,routeTimer=0,toastTimer=0,loading=false;
let motionPaused=false;
try{motionPaused=localStorage.getItem('lma-motion-paused')==='true';}catch{}
setMotion(motionPaused);
const human=s=>String(s??'').replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase());
const n=(v,d=2)=>v==null?'—':Number(v).toLocaleString('en-US',{maximumFractionDigits:d});
const money=v=>v==null?'—':Number(v).toLocaleString('en-US',{style:'currency',currency:'USD',minimumFractionDigits:2,maximumFractionDigits:2});
const pct=(v,d=1)=>v==null?'—':`${n(v*100,d)}%`;
const date=v=>{if(!v)return 'Not recorded';const d=new Date(v);return Number.isNaN(+d)?String(v):d.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});};
const datetime=v=>{if(!v)return 'Not recorded';const d=new Date(v);return Number.isNaN(+d)?String(v):`${date(v)} · ${d.toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit'})}`;};
const badge=(value,kind='')=>`<span class="pill ${kind}">${esc(human(value))}</span>`;
const status=v=>badge(v??'Not recorded',/fail|reject|veto|blocked|error/i.test(v)?'negative':/pending|skip|hold/i.test(v)?'gold':'');
const short=v=>!v?'—':String(v).length>24?`${String(v).slice(0,12)}…${String(v).slice(-6)}`:String(v);
const titleOf=id=>data?.snapshots.find(s=>s.market.market_id===id)?.market.title||id||'Unlinked record';
const latestMarkets=()=>Array.from(new Map([...data.snapshots].reverse().map(s=>[s.market.market_id,s])).values());
const heading=(k,title,description,aside='')=>`<div class="page-heading"><div><span class="eyebrow">${esc(k)}</span><h1>${esc(title)}</h1><p>${esc(description)}</p></div>${aside?`<span class="page-number">${aside}</span>`:''}</div>`;
const metric=(label,value,note='')=>`<div class="stat-card"><div class="metric-label">${esc(label)}</div><div class="metric-value">${value}</div>${note?`<div class="metric-note">${esc(note)}</div>`:''}</div>`;
const empty=(title,description,command='')=>`<div class="panel empty"><div class="empty-symbol">∅</div><h2>${esc(title)}</h2><p>${esc(description)}</p>${command?`<code>${esc(command)}</code>`:''}</div>`;
const tabs=(items,selected)=>`<div class="tabs" role="tablist">${items.map(([id,label])=>`<button class="tab" role="tab" data-action="tab" data-value="${id}" aria-selected="${id===selected}">${esc(label)}</button>`).join('')}</div>`;
const safeUrl=url=>{try{const u=new URL(url);return ['https:','http:'].includes(u.protocol)?u.href:null;}catch{return null;}};
function registerDetail(record,title,type='record') {const id=details.length;details.push({record,title,type});return id;}
function openButton(record,title,type='record'){return `<button class="row-open" data-action="detail" data-value="${registerDetail(record,title,type)}" aria-label="View ${esc(title)}">${icon('chevron')}</button>`;}
function toolbar(placeholder,filters=[]){return `<div class="toolbar"><label class="search">${icon('search')}<input id="table-search" type="search" placeholder="${esc(placeholder)}" aria-label="${esc(placeholder)}" value="${esc(state.search)}"></label>${filters.length?`<select id="table-filter" class="select" aria-label="Filter records"><option value="">All records</option>${filters.map(v=>`<option value="${esc(v)}" ${state.filter===v?'selected':''}>${esc(human(v))}</option>`).join('')}</select>`:''}<button class="button export" data-action="export">${icon('export')}Export CSV</button></div>`;}
function table(rows,columns,{title='Records',subtitle='',filterKey='',emptyTitle='No records yet',emptyDescription='Records will appear here after they are created by the local workflow.',detailType='record'}={}) {
  activeTable={rows,columns,title,subtitle,filterKey,emptyTitle,emptyDescription,detailType};
  return `<div id="table-host">${tableContent()}</div>`;
}
const sortKeys={'Source':'platform','Probability':'market_implied_probability','Bid / Ask':'best_bid','Action':'action','Estimated / Market':'agent_probability','Edge':'edge','Confidence':'confidence','Decision':'status','Position limit':'max_position_usd','Portfolio limit':'max_position_pct','Reason':'reasons','Status':'status','Side':'side','Quantity':'quantity','Average price':'average_price','Realized P&L':'realized_pnl','Fees':'fees','Fill price':'fill_price','Brief':'brief_id','Signal':'signal_action','Risk':'risk_approved','Order':'order_status','Starting cash':'starting_cash','Ending cash':'ending_cash','Orders':'orders','Mode':'dry_run','Portfolio value':'portfolio_value','Cash balance':'cash_balance','Unrealized P&L':'unrealized_pnl','Exposure':'exposure_pct','Market value':'market_value','Price':'price','Closing':'is_closing','Reasons':'reasons'};
function filteredRows(){
  if(!activeTable)return[];
  const rows=activeTable.rows.filter(r=>(!state.search||JSON.stringify(r).toLowerCase().includes(state.search.toLowerCase()))&&(!state.filter||String(r[activeTable.filterKey])===state.filter));
  if(state.sort===null)return rows;
  const col=activeTable.columns[state.sort];if(!col)return rows;
  const value=r=>col.sortValue?col.sortValue(r):r[col.key||sortKeys[col.label]];
  return rows.sort((a,b)=>{const x=value(a),y=value(b);if(x==null)return y==null?0:1;if(y==null)return -1;return state.direction*(typeof x==='number'&&typeof y==='number'?x-y:String(x).localeCompare(String(y),'en',{numeric:true}));});
}
function tableContent(){
  const t=activeTable,rows=filteredRows(),size=8,pages=Math.max(1,Math.ceil(rows.length/size));
  state.pageIndex=Math.min(state.pageIndex,pages-1);
  if(!rows.length)return empty(t.rows.length?'No matching records':t.emptyTitle,t.rows.length?'Try a different search or clear the filter.':t.emptyDescription);
  const first=state.pageIndex*size,last=Math.min(first+size,rows.length);
  return `<div class="panel"><div class="panel-head"><h2>${esc(t.title)} <span class="muted">(${rows.length})</span></h2><small>${esc(t.subtitle)}</small></div><div class="table-scroll"><table><thead><tr>${t.columns.map((c,i)=>`<th scope="col" aria-sort="${state.sort===i?(state.direction===1?'ascending':'descending'):'none'}"><button class="sort-button" data-action="sort" data-value="${i}" aria-label="Sort by ${esc(c.label)}">${esc(c.label)}<span aria-hidden="true">${state.sort===i?(state.direction===1?'↑':'↓'):'↕'}</span></button></th>`).join('')}<th scope="col"><span class="sr-only">Details</span></th></tr></thead><tbody>${rows.slice(first,last).map(r=>`<tr>${t.columns.map(c=>`<td class="${c.class||''}">${c.render?c.render(r):esc(r[c.key]??'—')}</td>`).join('')}<td>${openButton(r,r.market_id?titleOf(r.market_id):t.title,t.detailType)}</td></tr>`).join('')}</tbody></table></div><div class="pagination"><span>${first+1}–${last} of ${rows.length} records</span><div><button class="icon-button" data-action="previous" ${state.pageIndex===0?'disabled':''} aria-label="Previous page">${icon('left')}</button><span>${state.pageIndex+1} / ${pages}</span><button class="icon-button" data-action="next" ${state.pageIndex>=pages-1?'disabled':''} aria-label="Next page">${icon('chevron')}</button></div></div></div>`;
}
function refreshTable(){if($('#table-host'))$('#table-host').innerHTML=tableContent();}
const marketColumn={label:'Market',class:'title-cell',sortValue:r=>titleOf(r.market_id),render:r=>`${esc(titleOf(r.market_id))}<span class="cell-subtitle mono">${esc(short(r.market_id))}</span>`};
const timeColumn=(key='created_at')=>({label:'Recorded',sortValue:r=>r[key]?+new Date(r[key]):null,render:r=>esc(datetime(r[key]))});
const idColumn=key=>({label:'Reference',class:'mono',key,render:r=>esc(short(r[key]))});

function overview(){
  const markets=latestMarkets(),latest=markets[0],portfolio=data.portfolio_snapshots[0];
  return `<section class="hero"><span class="eyebrow">THE MARKET, IN PERSPECTIVE</span><h1>Insight.<br><em>In balance.</em></h1><p>A considered view of your research<br>and paper portfolio. Room to think.</p><a class="text-link" href="#watchlist">Explore your markets ${icon('arrow')}</a><div class="sculpture-caption">CHARGING BULL <em>A study in conviction</em></div></section>
  <div class="overview-metrics"><div class="overview-metric"><div class="metric-label">Markets followed</div><div class="metric-value">${data.meta.fixture_preview?'0':markets.length}<small>markets</small></div><div class="metric-note">${data.meta.fixture_preview?'Fixture preview available':'Unique markets in local records'}</div></div><div class="overview-metric"><div class="metric-label">Research library</div><div class="metric-value">${data.meta.counts.research_briefs||0}<small>briefs</small></div><div class="metric-note">Evidence-led local research</div></div><div class="overview-metric"><div class="metric-label">Paper portfolio</div><div class="metric-value">${portfolio?money(portfolio.portfolio_value):'—'}</div><div class="metric-note">${portfolio?`Recorded ${esc(date(portfolio.as_of))}`:'No portfolio snapshot yet'}</div></div></div>
  <div class="section-heading"><h2>On your radar</h2><a href="#watchlist">View watchlist ${icon('arrow')}</a></div>
  ${latest?`<a href="#watchlist" class="featured-market"><div class="market-monogram">m</div><div><h3>${esc(latest.market.title)}</h3><div class="subline">${badge(latest.market.platform,latest.market.platform==='fixture'?'gold':'')}<span>${esc(human(latest.market.status))}</span><span>·</span><span>${esc(date(latest.as_of))}</span></div></div><div class="featured-price"><strong>${pct(latest.market_implied_probability,0)}</strong><small>IMPLIED PROBABILITY</small></div>${icon('chevron')}</a>`:''}
  <p class="overview-note">${data.meta.fixture_preview?'Preview from the deterministic fixture. No market snapshots have been saved.':'Showing saved observations. Fixture records are demonstrations; prices are not a live feed.'}</p>`;
}
function watchlist(){
  const tab=state.tab==='history'?'history':'markets';
  const rows=(tab==='history'?data.snapshots:latestMarkets()).map(s=>({...s,market_id:s.market.market_id,platform:s.market.platform,status:s.market.status}));
  return heading('RESEARCH / 01','Watchlist','A clear view of your markets. Open a record to inspect its complete snapshot.',`${latestMarkets().length} market${latestMarkets().length===1?'':'s'}`)+
    (data.meta.fixture_preview?'<div class="notice">Fixture preview · No saved market snapshots. This example is not a live quote.</div>':'')+
    tabs([['markets','Latest by market'],['history','Snapshot history']],tab)+toolbar('Search markets…',[...new Set(rows.map(r=>r.platform))])+
    table(rows,[marketColumn,{label:'Source',render:r=>badge(r.platform,r.platform==='fixture'?'gold':'')},{label:'Probability',class:'num',render:r=>pct(r.market_implied_probability)},{label:'Bid / Ask',class:'num',render:r=>`${n(r.best_bid,3)} / ${n(r.best_ask,3)}`},{label:'Spread',class:'num',sortValue:r=>r.best_ask!=null&&r.best_bid!=null?r.best_ask-r.best_bid:null,render:r=>pct(r.best_ask!=null&&r.best_bid!=null?r.best_ask-r.best_bid:null)},timeColumn('as_of')],{title:tab==='history'?'Saved observations':'Market observations',subtitle:'Saved data · not a live feed',filterKey:'platform'})+
    '<p class="note">The latest view groups snapshots by market. Snapshot history retains every loaded observation.</p>';
}
function briefs(){
  if(!data.briefs.length)return heading('RESEARCH / 02','Market Brief','Research, evidence and the reasoning behind every signal.')+empty('A place for your research','Generate a local brief to explore its thesis, supporting evidence and uncertainties.','lma generate-brief --fixture data/fixtures/demo_market.json');
  state.brief=Math.min(state.brief,data.briefs.length-1);const b=data.briefs[state.brief];
  const tab=['counter','notes','record'].includes(state.tab)?state.tab:'evidence';
  let content='';
  if(tab==='evidence'||tab==='counter'){
    const list=tab==='counter'?b.counter_evidence:b.evidence;
    content=list.length?list.map(v=>`<article class="evidence-card"><span class="eyebrow">${esc(v.source)}</span><h3>${esc(v.title)}</h3><p>${esc(v.summary)}</p><div class="evidence-meta"><span>Published ${esc(date(v.published_at))}</span><span>Credibility ${pct(v.credibility_score)}</span><span>Relevance ${pct(v.relevance_score)}</span></div>${safeUrl(v.url)?`<p><a href="${esc(safeUrl(v.url))}" target="_blank" rel="noopener noreferrer">Read source ↗</a></p>`:''}</article>`).join(''):'<p>No evidence recorded in this category.</p>';
  }else if(tab==='notes')content=`<h3>Rationale</h3><p>${esc(b.rationale)}</p><h3>Uncertainty</h3>${listHtml(b.uncertainty_notes)}<h3>Trading constraints</h3>${listHtml(b.must_not_trade_reasons)}`;
  else content=`${definitionList(b,true)}${rawHtml(b)}`;
  return heading('RESEARCH / 02','Market Brief','The thesis, the evidence, and the other side of the argument.')+
    `<div class="brief-layout"><div class="brief-list" aria-label="Select a research brief">${data.briefs.map((v,i)=>`<button class="brief-choice" data-action="brief" data-value="${i}" aria-pressed="${i===state.brief}"><span class="eyebrow">RESEARCH NOTE ${String(i+1).padStart(2,'0')}</span><h3>${esc(titleOf(v.market_id))}</h3><small>${esc(date(v.created_at))}</small></button>`).join('')}</div><article class="panel panel-pad brief-content"><div class="badge-line">${status(b.recommended_action)}<span class="subline">${esc(datetime(b.created_at))}</span></div><h2>${esc(b.thesis)}</h2><p>${esc(b.rationale)}</p><div class="stat-grid">${metric('Estimated probability',pct(b.estimated_probability))}${metric('Market probability',pct(b.market_implied_probability))}${metric('Confidence',pct(b.confidence))}</div>${tabs([['evidence',`Evidence · ${b.evidence.length}`],['counter',`Counterpoint · ${b.counter_evidence.length}`],['notes','Notes'],['record','Full record']],tab)}<div class="detail-section">${content}</div><button class="button" data-action="detail" data-value="${registerDetail(b,b.thesis)}">Open complete brief ${icon('arrow')}</button></article></div>`;
}
function signals(){return heading('RESEARCH / 03','Signals','Trace each research signal to its source, confidence and estimated edge.')+toolbar('Search signals…',[...new Set(data.signals.map(r=>r.action))])+table(data.signals,[marketColumn,{label:'Action',render:r=>status(r.action)},{label:'Estimated / Market',render:r=>`${pct(r.agent_probability)} / ${pct(r.market_probability)}`},{label:'Edge',render:r=>pct(r.edge)},{label:'Confidence',render:r=>pct(r.confidence)},timeColumn()],{title:'Research signals',filterKey:'action',emptyTitle:'No signals recorded',emptyDescription:'Signals from your local research workflow will appear here.'});}
function risk(){
  const approved=data.risk_decisions.filter(r=>r.status==='approved').length;
  return heading('PORTFOLIO / 01','Risk Decisions','Understand each decision, its constraints, and the reasons behind it.')+`<div class="stat-grid">${metric('Decisions',n(data.risk_decisions.length,0),'Loaded local records')}${metric('Approved',n(approved,0),'Paper trading only')}${metric('Other decisions',n(data.risk_decisions.length-approved,0),'Inspect individual statuses')}${metric('Human approval',data.settings.human_approval_required?'Required':'Disabled','Configured policy')}</div>`+toolbar('Search decisions or reasons…',[...new Set(data.risk_decisions.map(r=>r.status))])+table(data.risk_decisions,[idColumn('risk_decision_id'),{label:'Decision',render:r=>status(r.status)},{label:'Position limit',render:r=>money(r.max_position_usd)},{label:'Portfolio limit',render:r=>pct(r.max_position_pct)},{label:'Reason',class:'title-cell',render:r=>esc((r.reasons||[]).join(' · '))},timeColumn()],{title:'Risk review',filterKey:'status',emptyTitle:'No risk decisions yet',emptyDescription:'Recorded risk decisions and veto reasons will appear here.'});
}
function ledger(){
  const tab=state.tab==='positions'?'positions':'orders',positions=tab==='positions';
  const rows=positions?data.positions.map(p=>({...p,status:p.closed_at?'closed':'open'})):data.orders;
  const columns=positions?[marketColumn,{label:'Status',render:r=>status(r.status)},{label:'Quantity',render:r=>n(r.quantity,4)},{label:'Average price',render:r=>n(r.average_price,4)},{label:'Realized P&L',render:r=>money(r.realized_pnl)},{label:'Fees',render:r=>money(r.fees)},timeColumn('opened_at')]:[marketColumn,{label:'Side',render:r=>badge(r.side)},{label:'Quantity',render:r=>n(r.quantity,4)},{label:'Fill price',render:r=>n(r.fill_price,4)},{label:'Fees',render:r=>money(r.fees)},{label:'Status',render:r=>status(r.status)},timeColumn()];
  return heading('PORTFOLIO / 02','Paper Ledger','Your simulated orders and positions, with the complete approval trail.')+tabs([['orders',`Orders · ${data.orders.length}`],['positions',`Positions · ${data.positions.length}`]],tab)+toolbar('Search ledger…',[...new Set(rows.map(r=>r.status))])+table(rows,columns,{title:positions?'Paper positions':'Paper orders',filterKey:'status',emptyTitle:positions?'No paper positions':'No paper orders',emptyDescription:'Your paper workflow records will appear here once available.'});
}
function audit(){
  return heading('PORTFOLIO / 03','Audit Chain','Follow a decision from research to its recorded paper order.')+`<div class="audit-flow">${[['Research',data.briefs.length,'briefs'],['Signal',data.signals.length,'signals'],['Risk review',data.risk_decisions.length,'decisions'],['Paper order',data.orders.length,'orders']].map(([label,count,suffix],i)=>`${i?`<span class="flow-arrow">${icon('arrow')}</span>`:''}<div class="audit-stage"><span class="eyebrow">${label}</span><strong>${count}</strong><span>${suffix} loaded</span></div>`).join('')}</div>`+toolbar('Search any linked reference…')+table(data.audit,[marketColumn,{label:'Brief',class:'mono',render:r=>esc(short(r.brief_id))},{label:'Signal',render:r=>status(r.signal_action||'Unlinked')},{label:'Risk',render:r=>r.risk_approved===null?badge('Unlinked','neutral'):badge(r.risk_approved?'Approved':'Not approved',r.risk_approved?'':'negative')},{label:'Order',render:r=>status(r.order_status||'No order')}],{title:'Linked decision records',subtitle:'Open a row to inspect all four stages',detailType:'audit',emptyTitle:'No audit chain yet',emptyDescription:'The complete research-to-paper-order trail will appear after running the local workflow.'});
}
function chart(snapshots){
  const pts=[...snapshots].filter(s=>s.portfolio_value!=null&&s.as_of).sort((a,b)=>new Date(a.as_of)-new Date(b.as_of));
  if(pts.length<2)return '<p class="chart-caption">At least two portfolio snapshots are needed for a history chart.</p>';
  const vals=pts.map(s=>s.portfolio_value),lo=Math.min(...vals),hi=Math.max(...vals),span=hi-lo||Math.max(1,hi*.01),min=lo-span*.2,max=hi+span*.2;
  const times=pts.map(s=>+new Date(s.as_of)),t0=times[0],tspan=times.at(-1)-t0||1;
  const xy=pts.map((s,i)=>[65+(times[i]-t0)/tspan*805,145-(s.portfolio_value-min)/(max-min)*110]);
  return `<svg class="chart" viewBox="0 0 900 180" role="img" aria-label="Recorded paper portfolio values, ${esc(date(pts[0].as_of))} to ${esc(date(pts.at(-1).as_of))}">${[0,1,2].map(i=>`<line x1="65" x2="870" y1="${35+i*55}" y2="${35+i*55}" stroke="#dfe7d4" stroke-dasharray="3 5"/><text x="0" y="${39+i*55}">${esc(money(max-i*(max-min)/2))}</text>`).join('')}<polyline points="${xy.map(p=>p.join(',')).join(' ')}" fill="none" stroke="#82936a" stroke-width="2"/>${xy.map(([x,y],i)=>`<circle cx="${x}" cy="${y}" r="3" fill="#82936a"><title>${esc(datetime(pts[i].as_of))}: ${money(pts[i].portfolio_value)}</title></circle>`).join('')}<text x="65" y="173">${esc(date(pts[0].as_of))}</text><text x="870" y="173" text-anchor="end">${esc(date(pts.at(-1).as_of))}</text></svg><p class="chart-caption">Actual saved snapshots. Connecting lines only show the order of observations; this is not a strategy return curve.</p>`;
}
function performancePage(){
  const r=data.reports[Math.min(state.report,data.reports.length-1)];
  let content=heading('PORTFOLIO / 04','Performance Report','A measured look at your recorded paper portfolio and its costs.');
  if(r)content+=`<div class="badge-line">${badge('Paper results','gold')}<span class="subline">Report as of ${esc(datetime(r.as_of))}</span><select id="report-select" class="select" aria-label="Select performance report">${data.reports.map((v,i)=>`<option value="${i}" ${i===state.report?'selected':''}>${esc(datetime(v.as_of))}</option>`).join('')}</select></div><div class="stat-grid">${metric('Ending cash',money(r.ending_cash),'As recorded in this report')}${metric('Realized P&L',money(r.realized_pnl),'Paper accounting')}${metric('Unrealized P&L',money(r.unrealized_pnl),'As recorded in this report')}${metric('Total fees',money(r.total_fees),`${r.orders} orders · ${r.open_positions} open positions`)}</div>`;
  else content+=empty('No performance reports','Generate a paper report from your local workflow to inspect balances and costs.','lma report-daily');
  if(data.portfolio_snapshots.length)content+=`<div class="panel history-chart"><h2>Portfolio observations</h2>${chart(data.portfolio_snapshots)}</div><p class="note">Portfolio snapshots and performance reports have independent timestamps and may describe different workflow runs.</p>`;
  if(r)content+=`<div class="report-notes">${listHtml(r.notes)}</div>`+toolbar('Search report records…')+table(data.reports,[idColumn('report_id'),{label:'Starting cash',render:r=>money(r.starting_cash)},{label:'Ending cash',render:r=>money(r.ending_cash)},{label:'Orders',key:'orders'},{label:'Fees',render:r=>money(r.total_fees)},timeColumn('as_of')],{title:'Saved reports'});
  return content;
}
function operations(){
  const op=data.operations,s=op.portfolio_summary,has=Boolean(s.snapshot_id);
  const tab=['portfolio','positions','orders','fills','gates'].includes(state.tab)?state.tab:'runs';
  const datasets={runs:op.run_rows,portfolio:has?[s]:[],positions:op.open_positions,orders:op.paper_orders,fills:op.paper_fills,gates:op.risk_gate_decisions};
  const labels={runs:'Recent runs',portfolio:'Latest portfolio snapshot',positions:'Open paper positions',orders:'Recent paper orders',fills:'Recent paper fills',gates:'Risk gate decisions'};
  const cols={
    runs:[idColumn('run_id'),{label:'Status',render:r=>status(r.status)},{label:'Mode',render:r=>badge(r.dry_run?'Dry run':'Paper')},marketColumn,{label:'Reason',class:'title-cell',key:'reasons'},timeColumn()],
    portfolio:[idColumn('snapshot_id'),{label:'Portfolio value',render:r=>money(r.portfolio_value)},{label:'Cash balance',render:r=>money(r.cash_balance)},{label:'Realized P&L',render:r=>money(r.realized_pnl)},{label:'Unrealized P&L',render:r=>money(r.unrealized_pnl)},{label:'Exposure',render:r=>pct(r.exposure_pct)},timeColumn('as_of')],
    positions:[marketColumn,{label:'Side',render:r=>badge(r.side)},{label:'Quantity',render:r=>n(r.quantity,4)},{label:'Average price',render:r=>n(r.average_price,4)},{label:'Market value',render:r=>money(r.market_value)},timeColumn('opened_at')],
    orders:[marketColumn,{label:'Side',render:r=>badge(r.side)},{label:'Quantity',render:r=>n(r.quantity,4)},{label:'Fill price',render:r=>n(r.fill_price,4)},{label:'Status',render:r=>status(r.status)},timeColumn()],
    fills:[idColumn('fill_id'),marketColumn,{label:'Quantity',render:r=>n(r.quantity,4)},{label:'Price',render:r=>n(r.price,4)},{label:'Fees',render:r=>money(r.fees)},{label:'Closing',render:r=>badge(r.is_closing?'Yes':'No')},timeColumn('filled_at')],
    gates:[idColumn('risk_gate_decision_id'),marketColumn,{label:'Status',render:r=>status(r.status)},{label:'Reasons',class:'title-cell',key:'reasons'},timeColumn()]
  };
  return heading('WORKSPACE / 01','Phase 7 Operations','Review run history, portfolio snapshots and paper execution records.')+`<div class="stat-grid">${metric('Latest run',op.latest_run?esc(human(op.latest_run.status)):'—',op.latest_run?date(op.latest_run.created_at):'No runs recorded')}${metric('Open positions',has?n(s.open_positions,0):'—','In the latest portfolio snapshot')}${metric('Portfolio value',has?money(s.portfolio_value):'—',has?date(s.as_of):'No snapshot recorded')}${metric('Exposure',has?pct(s.exposure_pct):'—','Of recorded portfolio value')}</div>`+tabs([['runs','Runs'],['portfolio','Portfolio'],['positions','Positions'],['orders','Orders'],['fills','Fills'],['gates','Risk gates']],tab)+toolbar('Search operation records…')+table(datasets[tab],cols[tab],{title:labels[tab],emptyTitle:`No ${labels[tab].toLowerCase()}`,emptyDescription:'This view displays records from the local Phase 7 workflow.'})+`<p class="note">Latest report path: <span class="mono">${esc(op.latest_report_path||'No report path recorded.')}</span></p><p class="note">Recent view: up to 25 runs and 100 records per execution category. All values are saved paper records.</p>`;
}
function settingsPage(){
  const s=data.settings;
  return heading('WORKSPACE / 02','Settings','Your local configuration, visible in one place.')+`<div class="settings-grid"><section class="panel panel-pad"><h2>Workspace</h2>${definitionList({database:s.db_path,raw_cache:s.raw_cache_dir,research_briefs:s.research_brief_dir,research_provider:s.llm_provider})}</section><section class="panel panel-pad"><h2>Execution policy</h2>${definitionList({real_money_enabled:s.real_money_enabled,allow_live_orders:s.allow_live_orders,human_approval_required:s.human_approval_required})}<p class="note">This dashboard provides read-only access to saved records.</p></section><section class="panel panel-pad"><h2>Risk parameters</h2>${definitionList(s.risk)}</section><section class="panel panel-pad"><h2>Risk gates</h2>${definitionList(s.risk_gates)}</section><section class="panel panel-pad full-width"><h2>Display & motion</h2><p class="note">The architectural bull shifts its perspective as you navigate. Your system’s reduced-motion preference is respected automatically.</p><button class="button" data-action="motion">${motionPaused?'Resume background motion':'Pause background motion'}</button><p class="note">Display preference is saved in this browser. Configuration values above are inspected here and managed through the local project.</p></section></div>`;
}
function listHtml(values){return values?.length?`<ul>${values.map(v=>`<li>${esc(typeof v==='object'?JSON.stringify(v):v)}</li>`).join('')}</ul>`:'<p class="muted">None recorded.</p>';}
function definitionList(record,primitivesOnly=false){return `<dl class="definition-list">${Object.entries(record).filter(([k,v])=>!k.startsWith('_')&&(!primitivesOnly||v===null||typeof v!=='object')).map(([k,v])=>`<div class="definition-row"><dt>${esc(human(k))}</dt><dd>${typeof v==='boolean'?badge(v?'Enabled':'Disabled',v?'':'neutral'):esc(v===null?'Not recorded':typeof v==='object'?JSON.stringify(v):v)}</dd></div>`).join('')}</dl>`;}
function rawHtml(record){return `<details class="raw-data"><summary>Inspect full JSON record</summary><pre>${esc(JSON.stringify(record,null,2))}</pre></details>`;}
function recordHtml(record){return definitionList(record,true)+Object.entries(record).filter(([k,v])=>!k.startsWith('_')&&v&&typeof v==='object').map(([k,v])=>`<section class="detail-section"><h3>${esc(human(k))}</h3>${Array.isArray(v)?(v.every(x=>typeof x!=='object')?listHtml(v):v.map(x=>`<details class="raw-data"><summary>${esc(x.title||x.evidence_id||'Nested record')}</summary><pre>${esc(JSON.stringify(x,null,2))}</pre></details>`).join('')):definitionList(v)}</section>`).join('');}
function showDetail(index){
  currentDetail=details[index];if(!currentDetail)return;
  const {record,title,type}=currentDetail;
  let body='';
  if(type==='audit')body=[['_brief','01 · Research brief'],['_signal','02 · Signal'],['_risk_decision','03 · Risk decision'],['_paper_order','04 · Paper order']].map(([k,label])=>`<section class="detail-section"><h3>${label}</h3>${record[k]?recordHtml(record[k]):'<p class="muted">No linked record for this stage.</p>'}</section>`).join('');
  else body=recordHtml(record);
  $('#detail-content').innerHTML=`<h2 id="detail-title" class="drawer-title">${esc(title)}</h2><p class="drawer-description">A complete view of the saved local record.</p>${body}${rawHtml(record)}<div class="drawer-actions"><button class="button" data-action="download-json">${icon('export')}Download JSON</button><button class="button" data-action="copy-json">Copy JSON</button></div>`;
  const dialog=$('#detail-dialog');if(!dialog.open)dialog.showModal();$('#close-detail').focus();scene.detail(true);
}
function render(){
  if(!data)return;details=[];activeTable=null;
  const renderers={overview,watchlist,briefs,signals,risk,ledger,audit,performance:performancePage,operations,settings:settingsPage};
  const countNotice=Object.values(data.meta.counts).some(c=>c>data.meta.record_limit)?`<p class="notice">This workspace contains more than ${data.meta.record_limit} records in a category. The dashboard loads the newest ${data.meta.record_limit}; older records remain in the local database.</p>`:'';
  $('#main').innerHTML=`<div class="page">${!data.meta.database_available?'<div class="notice">No local database found. The watchlist shows a fixture preview; other sections will remain empty until records are created.</div>':''}${state.page==='overview'?'':countNotice}${renderers[state.page]()}</div>`;
  document.title=`${names[state.page]} · Local Market Agent`;
}
function route(){
  const [requested,tab='']=location.hash.slice(1).split('/');
  const next=Object.hasOwn(names,requested)?requested:'overview';
  if($('#detail-dialog').open)$('#detail-dialog').close();
  state={...state,page:next,tab,search:'',filter:'',pageIndex:0,sort:null,direction:1};
  document.body.dataset.page=next;
  $('#breadcrumb-current').textContent=names[next];
  document.querySelectorAll('[data-page]').forEach(a=>{const active=a.dataset.page===next;a.classList.toggle('active',active);if(active)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  closeMenu();scene.navigate(next);scene.detail(Boolean(tab));clearTimeout(routeTimer);
  const old=$('#main .page');if(old)old.classList.add('leaving');
  routeTimer=setTimeout(()=>{render();window.scrollTo({top:0,behavior:'instant'});if(tab)document.querySelector('.tab[aria-selected="true"]')?.focus({preventScroll:true});},old&&!matchMedia('(prefers-reduced-motion: reduce)').matches?145:0);
}
async function load(){
  if(loading)return;loading=true;$('#refresh').classList.add('spinning');$('#refresh').disabled=true;
  try{
    const response=await fetch('/api/dashboard',{cache:'no-store',signal:AbortSignal.timeout(15000)});
    if(!response.ok)throw new Error('read failed');
    data=await response.json();render();
    $('#connection-status').innerHTML='<span class="status-dot"></span>Local workspace';
    $('#footer-status').textContent=`Loaded ${new Date(data.meta.loaded_at).toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit'})} · saved local data`;
  }catch{
    if(data){toast('Refresh failed. Showing the last loaded records.');$('#connection-status').textContent='Refresh unavailable';}
    else $('#main').innerHTML=`<div class="page">${empty('Workspace unavailable','The local data could not be loaded. Check that the dashboard server is running, then retry.')}<div class="section-heading"><button class="button primary" data-action="retry">Retry connection</button></div></div>`;
  }finally{loading=false;$('#refresh').classList.remove('spinning');$('#refresh').disabled=false;}
}
function toast(message){clearTimeout(toastTimer);$('#toast').textContent=message;$('#toast').classList.add('visible');toastTimer=setTimeout(()=>$('#toast').classList.remove('visible'),3200);}
function download(content,filename,type){const url=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function exportCsv(){
  if(!activeTable)return;const rows=filteredRows();if(!rows.length){toast('No records to export.');return;}
  const keys=[...new Set(rows.flatMap(r=>Object.keys(r).filter(k=>!k.startsWith('_'))))];
  const csv=v=>{let text=v==null?'':typeof v==='object'?JSON.stringify(v):String(v);if(/^[\s]*[=+@-]/.test(text)&&typeof v!=='number')text="'"+text;return `"${text.replace(/"/g,'""')}"`;};
  const content=[keys.map(csv).join(','),...rows.map(r=>keys.map(k=>csv(r[k])).join(','))].join('\r\n');
  download('\uFEFF'+content,`local-market-${state.page}-${state.tab||'records'}.csv`,'text/csv;charset=utf-8');toast(`Exported ${rows.length} records.`);
}
function setMotion(paused){motionPaused=paused;scene.setPaused(paused);$('#motion-toggle').innerHTML=icon(paused?'play':'pause');$('#motion-toggle').setAttribute('aria-label',paused?'Resume background motion':'Pause background motion');$('#motion-toggle').setAttribute('title',paused?'Resume background motion':'Pause background motion');$('#motion-toggle').setAttribute('aria-pressed',String(paused));try{localStorage.setItem('lma-motion-paused',String(paused));}catch{}}
const narrowScreen=matchMedia('(max-width:800px)');
function closeMenu(){$('#sidebar').classList.remove('open');$('#mobile-shade').classList.remove('active');$('#menu-toggle').setAttribute('aria-expanded','false');$('#sidebar').inert=narrowScreen.matches;}
document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-action]');if(!button)return;
  const {action,value}=button.dataset;
  if(action==='detail')showDetail(Number(value));
  if(action==='tab')location.hash=`${state.page}/${value}`;
  if(action==='brief'){state.brief=Number(value);render();scene.detail(false);}
  if(action==='previous'||action==='next'){state.pageIndex+=action==='next'?1:-1;refreshTable();}
  if(action==='export')exportCsv();
  if(action==='sort'){const i=Number(value);state.direction=state.sort===i?-state.direction:1;state.sort=i;state.pageIndex=0;refreshTable();document.querySelector(`.sort-button[data-value="${i}"]`)?.focus();}
  if(action==='retry')load();
  if(action==='motion'){setMotion(!motionPaused);render();}
  if(action==='download-json'&&currentDetail)download(JSON.stringify(currentDetail.record,null,2),'local-market-record.json','application/json');
  if(action==='copy-json'&&currentDetail){try{await navigator.clipboard.writeText(JSON.stringify(currentDetail.record,null,2));toast('Record copied.');}catch{toast('Copy unavailable. Use Download JSON instead.');}}
});
document.addEventListener('input',event=>{if(event.target.id==='table-search'){state.search=event.target.value;state.pageIndex=0;refreshTable();}});
document.addEventListener('change',event=>{if(event.target.id==='table-filter'){state.filter=event.target.value;state.pageIndex=0;refreshTable();}if(event.target.id==='report-select'){state.report=Number(event.target.value);render();}});
$('#refresh').addEventListener('click',load);
$('#motion-toggle').addEventListener('click',()=>{setMotion(!motionPaused);if(state.page==='settings')render();});
$('#menu-toggle').addEventListener('click',()=>{const open=!$('#sidebar').classList.contains('open');$('#sidebar').classList.toggle('open',open);$('#mobile-shade').classList.toggle('active',open);$('#menu-toggle').setAttribute('aria-expanded',String(open));$('#sidebar').inert=!open&&narrowScreen.matches;});
$('#mobile-shade').addEventListener('click',closeMenu);
$('#close-detail').addEventListener('click',()=>$('#detail-dialog').close());
$('#detail-dialog').addEventListener('close',()=>scene.detail(false));
$('#detail-dialog').addEventListener('click',e=>{if(e.target===$('#detail-dialog')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.target.close();}});
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'){const wasOpen=$('#sidebar').classList.contains('open');closeMenu();if(wasOpen)$('#menu-toggle').focus();}
  if(e.target.matches('[role="tab"]')&&['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){
    e.preventDefault();const all=[...e.target.parentElement.querySelectorAll('[role="tab"]')];
    const i=all.indexOf(e.target),next=e.key==='Home'?0:e.key==='End'?all.length-1:(i+(e.key==='ArrowRight'?1:-1)+all.length)%all.length;
    all[next].focus();all[next].click();
  }
});
narrowScreen.addEventListener('change',closeMenu);
$('.skip-link').addEventListener('click',e=>{e.preventDefault();$('#main').focus();});
window.addEventListener('hashchange',route);
route();load();
