'use strict';
const $ = s => document.querySelector(s);
let user = null, jobs = [], view = 'overview', selectedFile = null, selectedJob = null, timer = null;
const sample = 'device_id,temperature,battery_pct,site\nD-001,24.3,92,Shenzhen\nD-002,25.1,87,Shanghai\nD-003,,76,Shenzhen\nD-002,25.1,87,Shanghai\nD-004,23.8,95,Seattle\nD-005,26.2,,Seattle\n';
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const date = t => new Date(t * 1000).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
async function api(path, options = {}) {
  const response = await fetch(path, {...options, headers: {'Content-Type':'application/json', 'X-Portal-Request':'1', ...options.headers}});
  if (!response.ok) {
    let message = 'Request failed. Please try again.';
    try { const error = await response.json(); message = typeof error.detail === 'string' ? error.detail : 'Please check the entered values.'; } catch {}
    if (response.status === 401 && path !== '/api/login') signedOut();
    throw new Error(message);
  }
  return response.json();
}
function signedOut() {
  clearInterval(timer); timer = null; user = null;
  document.querySelectorAll('dialog[open]').forEach(d => d.close());
  $('#app-view').hidden = true; $('#login-view').hidden = false; $('#password').value = '';
}
function notice(text) { $('#notice').textContent = text; $('#notice').hidden = !text; }
async function signedIn() {
  user = await api('/api/me'); $('#login-view').hidden = true; $('#app-view').hidden = false;
  $('#user-name').textContent = user.name; $('#user-role').textContent = user.role;
  $('#avatar').textContent = user.name.split(' ').map(n => n[0]).join('');
  $('#org-label').textContent = user.org; $('#submit-org').textContent = user.org;
  $('#audit-nav').hidden = user.role !== 'admin';
  $('#access-note').textContent = user.role === 'partner' ? 'Organization-scoped access · Audited actions' : 'Internal cross-organization access · Audited actions';
  setView('overview'); await refresh();
  clearInterval(timer);
  timer = setInterval(async () => {
    if (document.hidden || !user) return;
    try { await refresh(); if (selectedJob && $('#detail-dialog').open) await loadDetail(selectedJob); } catch (e) { notice(e.message); }
  }, 3000);
}
$('#login-form').addEventListener('submit', async event => {
  event.preventDefault(); const button = $('#login-form button'); button.disabled = true; $('#login-error').textContent = '';
  try { await api('/api/login', {method:'POST',body:JSON.stringify({email:$('#email').value,password:$('#password').value})}); await signedIn(); }
  catch (e) { $('#login-error').textContent = e.message; } finally { button.disabled = false; }
});
$('#logout').addEventListener('click', async () => { try { await api('/api/logout',{method:'POST'}); signedOut(); } catch(e) { notice(e.message); } });
function setView(next) {
  view = next;
  document.querySelectorAll('[data-view]').forEach(b => b.classList.toggle('active',b.dataset.view === view));
  $('#page-label').textContent = {overview:'Overview',jobs:'All jobs',tools:'Tool library',audit:'Audit log'}[view];
  $('#page-title').textContent = {overview:'Workspace overview',jobs:'All validation jobs',tools:'Tool library',audit:'Audit log'}[view];
  $('#page-description').textContent = {overview:'From raw data to reliable results. Keep your validation work moving.',jobs:'Every validation run, from submission to report.',tools:'A focused collection of tools, ready for your team.',audit:'A record of who did what across the workspace.'}[view];
  $('#overview-section').hidden = view !== 'overview'; $('#jobs-section').hidden = !['overview','jobs'].includes(view);
  $('#tools-section').hidden = view !== 'tools'; $('#audit-section').hidden = view !== 'audit';
  $('#new-job').hidden = view === 'audit'; $('#table-title').firstChild.textContent = view === 'overview' ? 'Recent jobs ' : 'All jobs ';
  if(view === 'audit') loadAudit().catch(e => notice(e.message));
  renderJobs();
}
document.querySelectorAll('[data-view]').forEach(b => b.addEventListener('click', () => setView(b.dataset.view)));
async function refresh() {
  jobs = await api('/api/jobs'); notice('');
  $('#stat-total').textContent = jobs.length;
  $('#stat-completed').textContent = jobs.filter(j => j.status === 'completed').length;
  $('#stat-active').textContent = jobs.filter(j => ['running','queued'].includes(j.status)).length;
  $('#stat-attention').textContent = jobs.filter(j => j.status === 'failed' || j.report?.verdict === 'needs_attention').length;
  $('#nav-count').textContent = jobs.length; $('#job-count').textContent = jobs.length;
  renderJobs();
}
function renderJobs() {
  const query = $('#search').value.toLowerCase(), status = $('#status-filter').value;
  let filtered = jobs.filter(j => j.filename.toLowerCase().includes(query) && (!status || j.status === status));
  if (view === 'overview') filtered = filtered.slice(0,8);
  $('#jobs-body').innerHTML = filtered.map(j => {
    const quality = j.report ? (j.report.verdict === 'passed' ? '<span class="quality-ok">✓ Passed</span>' : '<span class="quality-warning">! Review findings</span>') : '<span>—</span>';
    return '<tr><td><span class="file-icon">CSV</span><div><strong title="'+esc(j.filename)+'">'+esc(j.filename)+'</strong><small>'+esc(j.id.slice(0,8))+' · Dataset validator</small></div></td><td>'+esc(j.org)+'</td><td><span class="badge '+esc(j.status)+'">'+esc(j.status)+'</span></td><td>'+quality+'</td><td>'+esc(date(j.created))+'</td><td><button class="open-job" data-job="'+esc(j.id)+'" aria-label="Open '+esc(j.filename)+'">↗</button></td></tr>';
  }).join('');
  $('#empty-state').hidden = filtered.length > 0;
  $('#empty-state h3').textContent = jobs.length ? 'No jobs match your search.' : 'A clear workspace. A fresh start.';
  $('#empty-state p').textContent = jobs.length ? 'Try another filename or status filter.' : 'Submit your first CSV or run the sample dataset to see Relay in action.';
  $('#empty-sample').hidden = jobs.length > 0;
  $('#result-count').textContent = 'Showing '+filtered.length+' of '+jobs.length+' jobs (latest 200)';
}
$('#search').addEventListener('input',renderJobs); $('#status-filter').addEventListener('change',renderJobs);
$('#jobs-body').addEventListener('click', async event => {
  const button = event.target.closest('[data-job]'); if (!button) return;
  try { selectedJob = button.dataset.job; await loadDetail(selectedJob); $('#detail-dialog').showModal(); } catch(e) { notice(e.message); }
});
function openSubmit(useSample = false) {
  selectedFile = useSample ? {name:'sample-device-readings.csv',content:sample} : null;
  $('#csv-file').value = ''; $('#file-label').textContent = selectedFile ? selectedFile.name : 'Choose a CSV or drop it here';
  $('#submit-error').textContent = ''; $('#submit-dialog').showModal();
}
['#new-job','#tool-run'].forEach(s => $(s).addEventListener('click',() => openSubmit()));
['#sample-job','#empty-sample'].forEach(s => $(s).addEventListener('click',() => openSubmit(true)));
$('#use-sample').addEventListener('click',() => { selectedFile = {name:'sample-device-readings.csv',content:sample}; $('#file-label').textContent = selectedFile.name; $('#csv-file').value=''; });
async function chooseFile(file) {
  $('#submit-error').textContent = ''; selectedFile = null;
  if(!file) return;
  if(!file.name.toLowerCase().endsWith('.csv') || file.size > 1_000_000) { $('#submit-error').textContent = 'Choose a CSV file under 1 MB.'; return; }
  selectedFile = {name:file.name,content:await file.text()}; $('#file-label').textContent = file.name;
}
$('#csv-file').addEventListener('change',event => chooseFile(event.target.files[0]).catch(e => $('#submit-error').textContent=e.message));
$('#dropzone').addEventListener('dragover',e => e.preventDefault());
$('#dropzone').addEventListener('drop',e => { e.preventDefault(); chooseFile(e.dataTransfer.files[0]).catch(err => $('#submit-error').textContent=err.message); });
document.querySelectorAll('.close-dialog').forEach(b => b.addEventListener('click',() => b.closest('dialog').close()));
$('#detail-dialog').addEventListener('close',() => { selectedJob = null; });
$('#submit-form').addEventListener('submit', async event => {
  event.preventDefault(); $('#submit-error').textContent = '';
  if(!selectedFile) { $('#submit-error').textContent = 'Choose a CSV or use the sample dataset.'; return; }
  $('#submit-button').disabled = true;
  try { await api('/api/jobs',{method:'POST',body:JSON.stringify({filename:selectedFile.name,content:selectedFile.content})}); $('#submit-dialog').close(); setView('jobs'); await refresh(); }
  catch(e) { $('#submit-error').textContent = e.message; } finally { $('#submit-button').disabled = false; }
});
async function loadDetail(id) {
  const job = await api('/api/jobs/'+id);
  $('#detail-title').textContent = job.filename;
  let html = '<p class="job-meta">'+esc(job.id)+'<br>'+esc(job.org)+' · '+esc(date(job.created))+' · Attempt '+job.attempts+' of 3</p><span class="badge '+esc(job.status)+'">'+esc(job.status)+'</span>';
  if(job.report) {
    const r = job.report;
    html += '<div class="report-stats"><div>Rows checked<strong>'+r.rows+'</strong></div><div>Missing cells<strong>'+r.missing_cells+'</strong></div><div>Duplicate rows<strong>'+r.duplicates+'</strong></div></div>';
    html += r.issues.length ? '<ul class="issue-list">'+r.issues.map(i=>'<li>'+esc(i)+'</li>').join('')+'</ul>' : '<p class="quality-ok">✓ All configured checks passed.</p>';
    html += '<div class="table-scroll"><table class="report-columns"><thead><tr><th>COLUMN</th><th>TYPE</th><th>MISSING</th><th>UNIQUE</th><th>RANGE</th></tr></thead><tbody>'+r.columns.map(c=>'<tr><td>'+esc(c.name)+'</td><td>'+esc(c.type)+'</td><td>'+c.missing+'</td><td>'+c.unique+'</td><td>'+(c.type==='number'?esc(c.min)+' – '+esc(c.max):'—')+'</td></tr>').join('')+'</tbody></table></div>';
  } else html += '<p class="muted">'+(job.error?esc(job.error):job.status==='cancelled'?'This validation was cancelled.':'The worker will process your dataset. This report updates automatically.')+'</p>';
  $('#detail-body').innerHTML = html;
  $('#detail-actions').innerHTML = job.status === 'completed' ? '<a class="primary" href="/api/jobs/'+esc(id)+'/report" download>Download JSON report ↓</a>' : ['queued','running'].includes(job.status) ? '<button id="cancel-job" class="secondary">Cancel job</button>' : '';
  const cancel = $('#cancel-job');
  if(cancel) cancel.addEventListener('click',async()=> { cancel.disabled=true; try { await api('/api/jobs/'+id+'/cancel',{method:'POST'}); await loadDetail(id); await refresh(); } catch(e) { notice(e.message); cancel.disabled=false; } });
}
async function loadAudit() {
  const entries = await api('/api/audit');
  $('#audit-body').innerHTML = entries.map(e=>'<tr><td>'+esc(date(e.created))+'</td><td>'+esc(e.actor)+'</td><td>'+esc(e.action)+'</td><td>'+esc(e.org)+'</td></tr>').join('');
}
signedIn().catch(() => signedOut());
