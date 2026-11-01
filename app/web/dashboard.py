"""Dependency-free authenticated dashboard and local operations API."""

from __future__ import annotations

import http.client
import json
import logging
import re
import signal
import threading
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import quote, unquote, urlparse, urlsplit

from app.config import Settings
from app.database.repository import Repository
from app.observability.monitor import MonitoringService
from app.orchestrator.engine import Orchestrator
from app.schemas.models import Project, ProjectRequest
from app.security.approval_manager import ApprovalManager
from app.security.audit_logger import AuditLogger
from app.security.auth import (
    AuthenticationError,
    AuthorizationDenied,
    AuthService,
    Permission,
    Role,
)
from app.web.preview import PreviewError
from app.web.workspace import ProjectDeletionError, WorkspaceService

LOGGER = logging.getLogger(__name__)
MAX_BODY_BYTES = 64 * 1024
MAX_PREVIEW_BYTES = 12 * 1024 * 1024
_ROOT_HTML_ATTRIBUTE = re.compile(r"((?:href|src|action)\s*=\s*['\"])/(?!/)", re.IGNORECASE)


def _rewrite_preview_html(payload: bytes, prefix: str) -> bytes:
    """Keep root-relative app assets inside the project preview proxy."""
    try:
        document = payload.decode("utf-8")
    except UnicodeDecodeError:
        return payload
    rewritten = _ROOT_HTML_ATTRIBUTE.sub(lambda match: match.group(1) + prefix + "/", document)
    return rewritten.encode("utf-8")


class DashboardError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(message)


def dashboard_html() -> str:
    """Return a self-contained chat-first workspace with no secret-bearing configuration."""
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>AI Dev Team Workspace</title>
<style>
:root{color-scheme:dark;--bg:#07111f;--panel:#0d1a2b;--panel2:#111f33;--line:#223752;--line-soft:#1a2c43;--text:#edf4ff;--muted:#8ea4bd;--accent:#6fe0c9;--blue:#76a7ff;--danger:#ff8c8c;--shadow:0 22px 70px #0007;--radius:14px}
*{box-sizing:border-box}html{min-width:320px;background:var(--bg)}body{margin:0;background:radial-gradient(circle at 38% -20%,#1b465d 0,#07111f 44%,#050b14 100%);font:14px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:var(--text);min-height:100vh;min-height:100dvh;-webkit-font-smoothing:antialiased}button,input,textarea{font:inherit}button{cursor:pointer}button:focus-visible,input:focus-visible,textarea:focus-visible{outline:2px solid var(--accent);outline-offset:2px}.hidden{display:none!important}.muted{color:var(--muted)}.eyebrow{color:var(--accent);font-size:10px;letter-spacing:.16em;text-transform:uppercase;font-weight:800}.button{background:linear-gradient(180deg,#19304a,#152943);color:var(--text);border:1px solid var(--line);border-radius:10px;padding:10px 13px;min-height:40px;transition:border-color .18s,background .18s,transform .18s}.button:hover{border-color:var(--accent);background:#1b3853}.button:active{transform:translateY(1px)}.button.primary{background:var(--accent);border-color:var(--accent);color:#05221d;font-weight:800}.button.primary:hover{background:#8bf0dd}.button.ghost{background:transparent}.button.danger{color:var(--danger)}
.login-screen{min-height:100vh;min-height:100dvh;display:grid;place-items:center;padding:24px}.login-card{width:min(420px,100%);background:#0d1a2bf2;border:1px solid var(--line);border-radius:20px;padding:34px;box-shadow:var(--shadow)}.brand{font-size:22px;font-weight:900;letter-spacing:-.03em;margin-bottom:30px}.brand span{color:var(--accent)}.field{display:grid;gap:7px;margin:16px 0}.field label{font-size:12px;color:var(--muted)}.field input,.field textarea,.search{width:100%;background:#081321;border:1px solid var(--line);border-radius:10px;color:var(--text);padding:12px;outline:none}.field input:focus,.field textarea:focus,.search:focus{border-color:var(--accent)}
.workspace{display:grid;grid-template-columns:minmax(225px,260px) minmax(390px,1.05fr) minmax(440px,1.5fr);height:100vh;height:100dvh;overflow:hidden}.sidebar,.chat-panel,.preview-panel{min-width:0}.sidebar{background:#07111fee;border-right:1px solid var(--line);display:flex;flex-direction:column;padding:20px 15px;gap:15px}.sidebar-top{display:flex;align-items:center;justify-content:space-between;gap:12px}.sidebar .brand{font-size:18px;margin:0}.sidebar-actions{display:flex;gap:7px}.sidebar .search{box-shadow:inset 0 0 0 1px #0002}.project-list{overflow:auto;display:grid;align-content:start;gap:8px;padding:1px 2px 8px 0}.project-item{border:1px solid transparent;border-radius:12px;padding:12px;display:grid;gap:6px;text-align:left;background:transparent;color:var(--text);transition:background .18s,border-color .18s,transform .18s}.project-item:hover,.project-item.selected{background:linear-gradient(135deg,#153049,#10243a);border-color:#2b5271}.project-item:hover{transform:translateY(-1px)}.project-name{font-weight:750;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.project-meta{font-size:11px;color:var(--muted);display:flex;justify-content:space-between;gap:8px}.project-meta span:first-child{color:var(--accent);font-weight:700}.side-bottom{margin-top:auto;border-top:1px solid var(--line);padding-top:14px;display:grid;gap:10px}.identity{font-size:12px;color:var(--muted);overflow:hidden;text-overflow:ellipsis}.empty{color:var(--muted);padding:28px 8px;text-align:center}
.chat-panel{display:flex;flex-direction:column;background:linear-gradient(180deg,#091525,#081321)}.workspace-header{min-height:78px;display:flex;align-items:center;justify-content:space-between;gap:14px;padding:16px 24px;border-bottom:1px solid var(--line);background:#091525e8}.workspace-title{min-width:0}.workspace-title h1{font-size:19px;letter-spacing:-.025em;margin:3px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.status{font-size:10px;padding:5px 8px;border-radius:99px;background:#17394a;color:var(--accent);white-space:nowrap;font-weight:800;letter-spacing:.04em}.header-actions{display:flex;gap:7px;flex-shrink:0}.chat-scroll{flex:1;overflow:auto;padding:24px;display:grid;align-content:start;gap:15px;scroll-behavior:smooth}.chat-message{max-width:88%;border:1px solid var(--line);border-radius:15px;padding:13px 15px;white-space:pre-wrap;overflow-wrap:anywhere;box-shadow:0 7px 20px #0002}.chat-message.user{justify-self:end;background:linear-gradient(135deg,#163c58,#14324a);border-color:#285777}.chat-message.assistant{justify-self:start;background:var(--panel2)}.chat-message.event{justify-self:stretch;background:#0b1928;border-style:dashed;color:var(--muted);font-size:12px;box-shadow:none}.chat-role{font-size:10px;color:var(--accent);font-weight:800;letter-spacing:.08em;text-transform:uppercase;margin-bottom:6px}.chat-time{font-size:10px;color:var(--muted);margin-top:8px}.composer{padding:15px 22px 18px;border-top:1px solid var(--line);background:#081321}.composer textarea{width:100%;resize:vertical;min-height:74px;max-height:190px;background:#0d1a2b;border:1px solid var(--line);border-radius:12px;color:var(--text);padding:13px;outline:none}.composer textarea:focus{border-color:var(--accent);box-shadow:0 0 0 3px #6fe0c91a}.composer-row{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-top:10px}.hint{font-size:11px;color:var(--muted)}
.preview-panel{background:#081321;border-left:1px solid var(--line);display:flex;flex-direction:column;min-height:0}.preview-toolbar{display:flex;gap:5px;padding:12px 15px;border-bottom:1px solid var(--line);overflow-x:auto;scrollbar-width:thin}.tab{border:1px solid transparent;border-radius:9px;background:transparent;color:var(--muted);padding:9px 10px;min-height:38px;white-space:nowrap}.tab:hover{color:var(--text);background:#10243a}.tab.active{background:#153049;border-color:#2d5777;color:var(--text);box-shadow:inset 0 -2px var(--accent)}.preview-actions{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:10px 15px;border-bottom:1px solid var(--line);background:#091525}.preview-actions .url{font-size:11px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.preview-actions .tools{display:flex;gap:6px;flex-shrink:0}.preview-actions .button{min-width:40px;padding-inline:10px}.preview-body{flex:1;min-height:0;overflow:auto;padding:16px}.preview-frame{display:block;width:100%;height:100%;min-height:480px;border:1px solid var(--line);border-radius:12px;background:white;box-shadow:0 14px 35px #0003}.preview-empty{height:100%;min-height:480px;display:grid;place-items:center;text-align:center;border:1px dashed var(--line);border-radius:14px;padding:30px;background:#0b1928}.preview-empty strong{display:block;font-size:17px;margin-bottom:8px}.data-card{border:1px solid var(--line);border-radius:12px;background:linear-gradient(145deg,#102039,#0d1a2b);padding:14px;margin-bottom:11px}.data-card h3{font-size:13px;margin:0 0 9px}.data-row{display:flex;justify-content:space-between;gap:12px;padding:8px 0;border-bottom:1px solid var(--line-soft);font-size:12px;overflow-wrap:anywhere}.data-row:last-child{border-bottom:0}.progress{height:7px;border-radius:8px;background:#1b3048;overflow:hidden;margin-top:9px}.progress i{display:block;height:100%;background:linear-gradient(90deg,var(--accent),#8bf0dd);border-radius:inherit}.approval{border:1px solid #826b36;background:#30291a;border-radius:12px;padding:12px;margin-bottom:9px}.approval button{margin-top:10px;margin-right:6px}.shot-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.shot-grid img{width:100%;border:1px solid var(--line);border-radius:10px;background:#fff}.artifact-link{display:block;color:var(--blue);padding:6px 0;text-decoration:none;overflow-wrap:anywhere}.artifact-link:hover{text-decoration:underline}.notice{position:fixed;left:50%;top:16px;transform:translateX(-50%);z-index:5;max-width:min(620px,calc(100% - 30px));padding:11px 15px;border:1px solid #8a7038;background:#3b321d;color:#f2c66d;border-radius:10px;box-shadow:var(--shadow)}.modal{position:fixed;inset:0;background:#000b;display:none;place-items:center;z-index:4;padding:16px}.modal.open{display:grid}.modal form{width:min(580px,100%);max-height:calc(100dvh - 32px);overflow:auto;background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:24px;box-shadow:var(--shadow)}.modal-actions{display:flex;justify-content:flex-end;gap:8px;flex-wrap:wrap}.preview-toggle{display:none}
@media(max-width:1199px){.workspace{grid-template-columns:230px minmax(330px,1fr)}.preview-panel{position:fixed;inset:0 0 0 auto;width:min(560px,100vw);height:100dvh;z-index:3;box-shadow:-20px 0 50px #0009;transform:translateX(102%);transition:transform .22s ease}.preview-panel.open{transform:translateX(0)}.preview-toggle{display:inline-flex!important}}
@media(max-width:760px){body{overflow:auto}.workspace{display:block;height:auto;min-height:100vh;min-height:100dvh;overflow:visible}.sidebar{height:auto;border-right:0;border-bottom:1px solid var(--line);padding:14px 13px;gap:12px}.sidebar .project-list{display:flex;overflow-x:auto;overflow-y:hidden;padding-bottom:4px;margin-right:-2px}.project-item{min-width:190px}.side-bottom{display:flex;align-items:center;justify-content:space-between;border:0;padding:0}.chat-panel{height:calc(100dvh - 180px);min-height:540px}.workspace-header{min-height:72px;padding:13px 15px}.workspace-title h1{font-size:17px}.chat-scroll{padding:17px 15px}.composer{padding:11px 13px 13px}.composer-row{align-items:flex-end}.hint{max-width:72%;line-height:1.35}.preview-panel{width:100vw}.preview-body{padding:12px}.preview-frame,.preview-empty{min-height:calc(100dvh - 150px)}.header-actions .button:not(.preview-toggle){display:none}.shot-grid{grid-template-columns:1fr}}
@media(max-width:420px){.login-card{padding:25px 20px}.sidebar .brand{font-size:17px}.project-item{min-width:174px;padding:11px}.workspace-header{gap:8px}.workspace-title h1{max-width:48vw}.status{font-size:9px}.chat-message{max-width:94%;padding:12px}.preview-toolbar{padding-inline:10px}.tab{padding-inline:9px}}
.button{display:inline-flex;align-items:center;justify-content:center;line-height:1}.sidebar-top .button{width:40px;padding-inline:0}.status{display:inline-flex;align-items:center;justify-content:center;min-height:24px;line-height:1}.project-meta span:first-child{display:inline-flex;align-items:center;min-height:22px;padding:3px 7px;border:1px solid #2b5271;border-radius:99px;background:#132a3e;line-height:1}
.plan-card{margin-top:14px;padding:14px;border:1px solid #2d5777;border-radius:12px;background:linear-gradient(145deg,#122b42,#0d1a2b);box-shadow:0 8px 24px #0002}.plan-card h3{margin:0 0 8px;font-size:14px}.plan-brief,.plan-architecture{margin:7px 0;color:var(--text)}.plan-section{margin-top:10px;border-top:1px solid var(--line-soft);padding-top:9px}.plan-section summary{cursor:pointer;color:var(--accent);font-size:12px;font-weight:800}.plan-section ul{margin:8px 0 0;padding-left:18px;color:var(--muted);font-size:12px}.plan-section li+li{margin-top:5px}.plan-task{margin-top:9px;padding:10px;border:1px solid var(--line-soft);border-radius:9px;background:#0b1928}.plan-task strong{font-size:12px}.plan-agent{display:inline-flex;margin-left:7px;padding:3px 6px;border:1px solid #2b5271;border-radius:99px;color:var(--accent);font-size:10px;text-transform:uppercase}.plan-task p{margin:7px 0;color:var(--muted);font-size:12px}
.chat-panel{min-height:0}.chat-scroll{min-height:0;overscroll-behavior:contain;scrollbar-gutter:stable;scroll-behavior:auto}.composer{flex-shrink:0}
.preview-close{display:none}@media(max-width:1199px){.preview-close{display:inline-flex}}
.project-item{grid-template-columns:minmax(0,1fr) 32px;align-items:center}.project-select{min-width:0;display:grid;gap:6px;text-align:left;background:transparent;border:0;color:inherit;padding:0}.project-select:focus-visible{outline:2px solid var(--accent);outline-offset:3px;border-radius:6px}.project-delete{width:32px;height:32px;display:inline-flex;align-items:center;justify-content:center;padding:0;border:1px solid transparent;border-radius:8px;background:transparent;color:var(--muted);font-size:16px;line-height:1}.project-delete:hover{color:var(--danger);border-color:#7c3f4d;background:#3a1f2b}.project-delete:focus-visible{outline:2px solid var(--danger);outline-offset:2px}.confirm-card{width:min(460px,100%);background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:24px;box-shadow:var(--shadow)}.confirm-card h2{margin:6px 0 8px}.confirm-card p{color:var(--muted);margin:0 0 18px;overflow-wrap:anywhere}
</style></head><body>
<section id="login" class="login-screen"><form id="login-form" class="login-card"><div class="brand">AI <span>Dev Team</span></div><div class="eyebrow">Private development workspace</div><h1>Sign in</h1><p class="muted">Access only the projects assigned to your account.</p><div id="login-error" class="notice hidden"></div><div class="field"><label for="login-user">Username</label><input id="login-user" autocomplete="username" required></div><div class="field"><label for="login-password">Password</label><input id="login-password" type="password" autocomplete="current-password" required></div><button class="button primary" type="submit">Open workspace</button></form></section>
<main id="workspace" class="workspace hidden"><aside class="sidebar"><div class="sidebar-top"><div class="brand">AI <span>Dev</span></div><button id="new-project" class="button primary" title="New project" aria-label="Create new project">+</button></div><input id="project-search" class="search" placeholder="Search projects" aria-label="Search projects"><div class="eyebrow">Projects</div><div id="project-list" class="project-list"></div><div class="side-bottom"><span id="identity" class="identity"></span><button id="logout" class="button ghost">Sign out</button></div></aside>
<section class="chat-panel"><header class="workspace-header"><div class="workspace-title"><div class="eyebrow">Project workspace</div><h1 id="project-title">Choose a project</h1></div><div class="header-actions"><span id="project-status" class="status">—</span><button id="preview-toggle" class="button preview-toggle" aria-label="Toggle application preview" aria-expanded="false">Preview</button><button id="refresh" class="button" aria-label="Refresh workspace">Refresh</button></div></header><div id="chat-scroll" class="chat-scroll"><div class="empty">Create or select a project to start a project-specific conversation.</div></div><form id="composer" class="composer"><textarea id="chat-input" placeholder="Describe what to build, change, or test…" maxlength="100000" disabled></textarea><div class="composer-row"><span class="hint">The Orchestrator coordinates the approved agents for this project.</span><button class="button primary" type="submit" disabled>Send</button></div></form></section>
<aside id="preview-panel" class="preview-panel"><nav id="tabs" class="preview-toolbar" aria-label="Project output"><button class="tab active" data-tab="preview" aria-selected="true">Live Preview</button><button class="tab" data-tab="final" aria-selected="false">Final Application</button><button class="tab" data-tab="qa" aria-selected="false">QA Results</button><button class="tab" data-tab="screenshots" aria-selected="false">Screenshots</button><button class="tab" data-tab="agents" aria-selected="false">Agent Activity</button><button class="tab" data-tab="artifacts" aria-selected="false">Build Artifacts</button></nav><div class="preview-actions"><span id="preview-url" class="url">No preview runtime</span><div class="tools"><button id="preview-close" class="button preview-close" aria-label="Close application preview">Close</button><button id="preview-refresh" class="button" aria-label="Refresh application preview">↻</button><button id="preview-open" class="button" aria-label="Open application preview in a new tab">Open</button></div></div><div id="preview-body" class="preview-body"><div class="preview-empty"><div><strong>Application preview</strong><span class="muted">Approve and run the project workflow to launch the actual application here.</span></div></div></div></aside></main>
<div id="notice" class="notice hidden"></div><div id="modal" class="modal"><form id="project-form"><div class="eyebrow">New isolated project</div><h2>Start a workspace</h2><div class="field"><label for="project-name">Project name</label><input id="project-name" name="name" required maxlength="120"></div><div class="field"><label for="project-requirement">What should the team build?</label><textarea id="project-requirement" name="requirement" rows="7" required minlength="10" maxlength="100000"></textarea></div><div class="modal-actions"><button type="button" id="cancel" class="button">Cancel</button><button class="button primary">Create project</button></div></form></div><div id="delete-modal" class="modal" role="dialog" aria-modal="true" aria-labelledby="delete-title"><section class="confirm-card"><div class="eyebrow">Permanent project deletion</div><h2 id="delete-title">Delete project?</h2><p id="delete-message">This removes the project workspace, worktrees, artifacts, preview state, and database records.</p><div class="modal-actions"><button type="button" id="delete-cancel" class="button">Cancel</button><button type="button" id="delete-confirm" class="button danger">Delete project</button></div></section></div>
<script>
const state={csrf:'',selected:'',projects:[],workspace:null,tab:'preview',search:''};let chatStickToBottom=true;
const $=id=>document.getElementById(id);const esc=v=>String(v??'');
async function api(path,options={}){const headers={...(options.headers||{}),'Content-Type':'application/json'};if(state.csrf)headers['X-CSRF-Token']=state.csrf;const response=await fetch(path,{...options,headers});let data={};try{data=await response.json()}catch(_e){}if(!response.ok)throw Error(data.error||'Request failed');return data}
function notice(message){const box=$('notice');box.textContent=message;box.classList.remove('hidden');setTimeout(()=>box.classList.add('hidden'),6000)}
function loginError(message){const box=$('login-error');box.textContent=message;box.classList.remove('hidden')}
function showApp(session){state.csrf=session.csrf;$('login').classList.add('hidden');$('workspace').classList.remove('hidden');$('identity').textContent=session.user.username+' · '+session.user.role;loadProjects()}
function clearNode(node){while(node.firstChild)node.removeChild(node.firstChild)}
function chip(text){const span=document.createElement('span');span.className='status';span.textContent=esc(text);return span}
function renderProjects(){const list=$('project-list');clearNode(list);const filtered=state.projects.filter(p=>(p.name+' '+p.project_id).toLowerCase().includes(state.search.toLowerCase()));if(!filtered.length){const e=document.createElement('div');e.className='empty';e.textContent='No projects yet.';list.append(e);return}filtered.forEach(project=>{const item=document.createElement('div');item.className='project-item '+(project.project_id===state.selected?'selected':'');const select=document.createElement('button');select.type='button';select.className='project-select';select.onclick=()=>selectProject(project.project_id);const name=document.createElement('span');name.className='project-name';name.textContent=project.name;const meta=document.createElement('span');meta.className='project-meta';const status=document.createElement('span');status.textContent=project.status;const count=document.createElement('span');count.textContent=project.completed_tasks+'/'+project.task_count+' tasks · '+project.progress_percentage+'%';meta.append(status,count);select.append(name,meta);const remove=document.createElement('button');remove.type='button';remove.className='project-delete';remove.title='Delete '+project.name;remove.setAttribute('aria-label','Delete '+project.name);remove.textContent='🗑';remove.onclick=()=>openDelete(project);item.append(select,remove);list.append(item)})}
function renderPlan(plan){const card=document.createElement('section');card.className='plan-card';const heading=document.createElement('h3');heading.textContent='Implementation plan';card.append(heading);const brief=document.createElement('p');brief.className='plan-brief';brief.textContent=plan.project_brief||'The Planning Agent prepared this implementation plan.';card.append(brief);const architecture=document.createElement('p');architecture.className='plan-architecture';architecture.textContent=plan.architecture?.summary||'';if(architecture.textContent)card.append(architecture);const addList=(label,items)=>{if(!Array.isArray(items)||!items.length)return;const details=document.createElement('details');details.className='plan-section';details.open=label==='Planned tasks';const summary=document.createElement('summary');summary.textContent=label+' ('+items.length+')';details.append(summary);const list=document.createElement('ul');items.forEach(value=>{const li=document.createElement('li');li.textContent=typeof value==='string'?value:JSON.stringify(value);list.append(li)});details.append(list);card.append(details)};addList('Functional requirements',plan.functional_requirements);addList('Non-functional requirements',plan.non_functional_requirements);if(Array.isArray(plan.tasks)&&plan.tasks.length){const details=document.createElement('details');details.className='plan-section';details.open=true;const summary=document.createElement('summary');summary.textContent='Planned tasks ('+plan.tasks.length+')';details.append(summary);plan.tasks.forEach(task=>{const taskCard=document.createElement('article');taskCard.className='plan-task';const title=document.createElement('strong');title.textContent=task.task_id+' · '+task.title;const agent=document.createElement('span');agent.className='plan-agent';agent.textContent=task.assigned_agent;const description=document.createElement('p');description.textContent=task.description;taskCard.append(title,agent,description);if(Array.isArray(task.acceptance_criteria)&&task.acceptance_criteria.length){const criteria=document.createElement('ul');task.acceptance_criteria.forEach(value=>{const li=document.createElement('li');li.textContent=value;criteria.append(li)});taskCard.append(criteria)}details.append(taskCard)});card.append(details)}return card}
function renderChat(messages){const box=$('chat-scroll');const stickToBottom=chatStickToBottom||box.scrollHeight-box.scrollTop-box.clientHeight<48;clearNode(box);box.onscroll=()=>{chatStickToBottom=box.scrollHeight-box.scrollTop-box.clientHeight<48};if(!messages.length){const e=document.createElement('div');e.className='empty';e.textContent='Tell the Orchestrator what to build in this project.';box.append(e);return}messages.forEach(message=>{const item=document.createElement('article');item.className='chat-message '+message.role;const role=document.createElement('div');role.className='chat-role';role.textContent=message.role==='user'?'You':message.role==='event'?'Workflow':'Orchestrator';const content=document.createElement('div');content.textContent=message.content;const time=document.createElement('div');time.className='chat-time';time.textContent=new Date(message.created_at).toLocaleString();item.append(role,content);if(message.metadata?.plan)item.append(renderPlan(message.metadata.plan));item.append(time);box.append(item)});if(stickToBottom){chatStickToBottom=true;requestAnimationFrame(()=>{box.scrollTop=box.scrollHeight})}}
function renderAgents(data){const box=document.createElement('div');const heading=document.createElement('h3');heading.textContent='Live agent status';box.append(heading);data.agents.forEach(agent=>{const card=document.createElement('div');card.className='data-card';const title=document.createElement('h3');title.textContent=agent.role+' · '+agent.status;const task=document.createElement('div');task.className='muted';task.textContent=agent.current_task?('Task: '+agent.current_task+' · '+(agent.current_task_status||'')):'Task: none assigned';const count=document.createElement('div');count.className='data-row';count.textContent=agent.completed_tasks+'/'+agent.task_count+' tasks · '+agent.progress_percentage+'% complete';const bar=document.createElement('div');bar.className='progress';const fill=document.createElement('i');fill.style.width=agent.progress_percentage+'%';bar.append(fill);card.append(title,task,count,bar);box.append(card)});return box}
function renderTasks(data){const box=document.createElement('div');const heading=document.createElement('h3');heading.textContent='Task progress';box.append(heading);if(!data.tasks.length){const empty=document.createElement('div');empty.className='empty';empty.textContent='No tasks created yet.';box.append(empty);return box}data.tasks.forEach(task=>{const card=document.createElement('div');card.className='data-card';const title=document.createElement('h3');title.textContent=task.title;const detail=document.createElement('div');detail.className='muted';detail.textContent=task.assigned_agent+' · '+task.status;card.append(title,detail);box.append(card)});return box}
function renderActivity(data){const box=document.createElement('div');const heading=document.createElement('h3');heading.textContent='Activity and execution details';box.append(heading);if(!data.activity.length&&!data.executions.length&&!data.tool_calls.length){const empty=document.createElement('div');empty.className='empty';empty.textContent='No activity recorded yet.';box.append(empty);return box}data.activity.slice(0,80).forEach(event=>{const row=document.createElement('div');row.className='data-row';const payload=event.payload||{};const detail=payload.error||payload.stage||payload.status||'';row.textContent=event.event_type+' · '+(event.actor_id||'system')+(event.task_id?' · '+event.task_id:'')+(detail?' · '+detail:'');box.append(row)});data.executions.slice(0,40).forEach(execution=>{const row=document.createElement('div');row.className='data-row';row.textContent='Execution '+execution.agent_id+' · '+execution.status+' · '+execution.task_id+(execution.error_classification?' · '+execution.error_classification:'');box.append(row)});data.tool_calls.slice(0,40).forEach(call=>{const row=document.createElement('div');row.className='data-row';row.textContent='Tool '+call.agent_id+' · '+call.tool_name+' · '+call.status+(call.task_id?' · '+call.task_id:'');box.append(row)});return box}
function renderQa(data){const box=document.createElement('div');const reports=data.artifacts.filter(a=>a.kind==='qa-report'||a.kind==='playwright-report');if(!reports.length){box.className='preview-empty';box.textContent='QA evidence will appear after the Testing Agent completes.';return box}reports.forEach(report=>{const card=document.createElement('div');card.className='data-card';const heading=document.createElement('h3');heading.textContent=report.kind;const pre=document.createElement('pre');pre.className='muted';pre.textContent=JSON.stringify(report.payload,null,2);card.append(heading,pre);box.append(card)});return box}
function renderScreenshots(data){const box=document.createElement('div');box.className='shot-grid';['desktop','tablet','mobile'].forEach(view=>{const img=document.createElement('img');img.alt=view+' application screenshot';img.src='/api/projects/'+encodeURIComponent(state.selected)+'/artifacts/screenshots/'+view+'/current.png';img.onerror=()=>{img.replaceWith(Object.assign(document.createElement('div'),{className:'empty',textContent:view+' screenshot pending'}))};box.append(img)});return box}
function renderArtifacts(data){const box=document.createElement('div');if(!data.artifacts.length){box.className='empty';box.textContent='No build artifacts yet.';return box}data.artifacts.forEach(artifact=>{const row=document.createElement('div');row.className='data-card';const title=document.createElement('h3');title.textContent=artifact.kind;const path=document.createElement('div');path.className='muted';path.textContent=artifact.path;row.append(title,path);box.append(row)});return box}
async function startPreview(){try{await api('/api/projects/'+encodeURIComponent(state.selected)+'/preview/start',{method:'POST',body:JSON.stringify({})});notice('Project preview started.');await loadWorkspace()}catch(error){notice('Preview could not start: '+error.message)}}
function renderRight(data){const body=$('preview-body');clearNode(body);document.querySelectorAll('.tab').forEach(tab=>{const active=tab.dataset.tab===state.tab;tab.classList.toggle('active',active);tab.setAttribute('aria-selected',String(active))});const preview=data.preview||{};$('preview-url').textContent=preview.status==='RUNNING'?preview.url:'No preview runtime';$('preview-open').disabled=preview.status!=='RUNNING';if(state.tab==='preview'||state.tab==='final'){if(preview.status==='RUNNING'&&preview.url){const frame=document.createElement('iframe');frame.className='preview-frame';frame.src=preview.url;frame.title=state.tab==='final'?'Final tested application':'Live application preview';body.append(frame)}else{const empty=document.createElement('div');empty.className='preview-empty';const inner=document.createElement('div');const strong=document.createElement('strong');strong.textContent=preview.status==='ERROR'?'Preview failed':'Application preview';const text=document.createElement('span');text.className='muted';text.textContent=preview.error||'Approve and run the project workflow to launch the actual application here.';inner.append(strong,text);if(preview.status!=='ERROR'||preview.error){const start=document.createElement('button');start.className='button primary';start.textContent='Start preview';start.onclick=startPreview;inner.append(start)}empty.append(inner);body.append(empty)}}else if(state.tab==='qa'){body.append(renderQa(data))}else if(state.tab==='screenshots'){body.append(renderScreenshots(data))}else if(state.tab==='agents'){body.append(renderAgents(data),renderTasks(data),renderActivity(data))}else{body.append(renderArtifacts(data))}}
function renderApprovals(data){const pending=data.approvals.filter(item=>item.decision==='PENDING');if(!pending.length)return;const box=$('chat-scroll');pending.forEach(approval=>{const card=document.createElement('section');card.className='approval';const title=document.createElement('strong');title.textContent='Approval required: '+approval.action;const detail=document.createElement('div');detail.className='muted';detail.textContent=approval.action==='approve_plan'?'Review the implementation plan above, then approve or reject it.':'Review this controlled action, then approve or reject it.';const actions=document.createElement('div');const approve=document.createElement('button');approve.className='button primary';approve.textContent='Approve';approve.onclick=()=>decide(approval.approval_id,'approve');const reject=document.createElement('button');reject.className='button danger';reject.textContent='Reject';reject.onclick=()=>decide(approval.approval_id,'reject');actions.append(approve,reject);card.append(title,detail,actions);box.append(card)});requestAnimationFrame(()=>{box.scrollTop=box.scrollHeight})}
async function decide(id,decision){try{const data=await api('/api/approvals/'+encodeURIComponent(id)+'/decision',{method:'POST',body:JSON.stringify({decision})});renderWorkspace(data)}catch(error){notice(error.message)}}
function renderWorkspace(data){state.workspace=data;$('project-title').textContent=data.project.name;const status=$('project-status');status.textContent=data.project.status;status.className='status status-'+String(data.project.status).toLowerCase();renderChat(data.chat);renderApprovals(data);renderRight(data);const input=$('chat-input');const send=document.querySelector('#composer button');input.disabled=false;send.disabled=false}
let pendingDelete=null;function openDelete(project){pendingDelete=project;$('delete-title').textContent='Delete '+project.name+'?';$('delete-message').textContent='This permanently removes '+project.name+' from the database and deletes its project workspace, worktrees, preview state, and build artifacts. This cannot be undone.';$('delete-modal').classList.add('open');$('delete-cancel').focus()}function closeDelete(){pendingDelete=null;$('delete-modal').classList.remove('open')}
async function confirmDelete(){if(!pendingDelete)return;const project=pendingDelete;const button=$('delete-confirm');button.disabled=true;button.textContent='Deleting…';try{const data=await api('/api/projects/'+encodeURIComponent(project.project_id),{method:'DELETE'});closeDelete();if(state.selected===project.project_id)state.selected='';await loadProjects();notice(data.name+' was deleted successfully.')}catch(error){button.disabled=false;button.textContent='Delete project';notice('Could not delete '+project.name+': '+error.message)}}
async function loadProjects(){try{const data=await api('/api/projects');state.projects=data.projects;if(state.selected&&!state.projects.some(project=>project.project_id===state.selected))state.selected='';renderProjects();if(!state.selected&&state.projects[0])state.selected=state.projects[0].project_id;if(state.selected)await loadWorkspace();else{state.workspace=null;$('project-title').textContent='Choose a project';$('project-status').textContent='—';$('chat-input').disabled=true;document.querySelector('#composer button').disabled=true;clearNode($('chat-scroll'));const empty=document.createElement('div');empty.className='empty';empty.textContent='Create or select a project to start a project-specific conversation.';$('chat-scroll').append(empty);renderRight({preview:{},artifacts:[]})}}catch(error){notice(error.message)}}
async function loadWorkspace(){if(!state.selected)return;try{const data=await api('/api/projects/'+encodeURIComponent(state.selected)+'/workspace');renderWorkspace(data);renderProjects()}catch(error){notice(error.message)}}
async function selectProject(projectId){state.selected=projectId;state.tab='preview';renderProjects();await loadWorkspace()}
$('login-form').onsubmit=async event=>{event.preventDefault();try{const session=await api('/api/auth/login',{method:'POST',body:JSON.stringify({username:$('login-user').value,password:$('login-password').value})});showApp(session)}catch(error){loginError(error.message)}};
$('logout').onclick=async()=>{try{await api('/api/auth/logout',{method:'POST'});location.reload()}catch(error){notice(error.message)}};
$('project-search').oninput=event=>{state.search=event.target.value;renderProjects()};$('refresh').onclick=loadWorkspace;const closePreview=()=>{$('preview-panel').classList.remove('open');$('preview-toggle').setAttribute('aria-expanded','false')};$('preview-toggle').onclick=()=>{const panel=$('preview-panel');const open=panel.classList.toggle('open');$('preview-toggle').setAttribute('aria-expanded',String(open))};$('preview-close').onclick=closePreview;$('preview-refresh').onclick=loadWorkspace;$('preview-open').onclick=()=>{if(state.workspace?.preview?.url)window.open(state.workspace.preview.url,'_blank','noopener')};
window.addEventListener('resize',()=>{const box=$('chat-scroll');if(box&&chatStickToBottom)requestAnimationFrame(()=>{box.scrollTop=box.scrollHeight})});
$('tabs').onclick=event=>{const tab=event.target.closest('.tab');if(tab){state.tab=tab.dataset.tab;renderRight(state.workspace)}};
$('composer').onsubmit=async event=>{event.preventDefault();if(!state.selected)return;const input=$('chat-input');const content=input.value.trim();if(!content)return;input.value='';try{const data=await api('/api/projects/'+encodeURIComponent(state.selected)+'/chat',{method:'POST',body:JSON.stringify({content})});renderWorkspace(data)}catch(error){notice(error.message)}};
$('new-project').onclick=()=>{$('modal').classList.add('open');$('project-name').focus()};$('cancel').onclick=()=>$('modal').classList.remove('open');$('project-form').onsubmit=async event=>{event.preventDefault();try{const data=await api('/api/projects',{method:'POST',body:JSON.stringify({name:$('project-name').value,requirement:$('project-requirement').value})});$('modal').classList.remove('open');$('project-form').reset();state.selected=data.project.project_id;await loadProjects()}catch(error){notice(error.message)}};$('delete-cancel').onclick=closeDelete;$('delete-confirm').onclick=confirmDelete;$('delete-modal').onclick=event=>{if(event.target===$('delete-modal'))closeDelete()};window.addEventListener('keydown',event=>{if(event.key==='Escape'&&$('delete-modal').classList.contains('open'))closeDelete()});
async function boot(){try{const session=await api('/api/auth/session');showApp(session)}catch(_error){$('login').classList.remove('hidden')}}boot();setInterval(()=>{if(!state.selected||document.hidden)return;loadProjects()},5000);
</script></body></html>"""


class DashboardApplication:
    def __init__(self, settings: Settings, repository: Repository) -> None:
        self.settings = settings
        self.repository = repository
        self.audit = AuditLogger(repository)
        self.auth = AuthService(repository, self.audit, settings.session_ttl_seconds)
        self.approvals = ApprovalManager(repository, self.audit)
        self.orchestrator = Orchestrator(settings, repository)
        self.monitor = MonitoringService(repository)
        self.workspace = WorkspaceService(settings, repository)

    def bootstrap_admin(self, username: str | None, password: str | None) -> None:
        if username and password and self.repository.get_user_by_username(username.lower()) is None:
            self.auth.create_user(username, password, Role.ADMIN)

    def project_for(self, user: Any, project_id: str) -> Project:
        project = self.repository.get_project(project_id)
        if project is None or not self.repository.has_project_access(
            project_id, user.user_id, admin=user.role is Role.ADMIN
        ):
            raise DashboardError(HTTPStatus.NOT_FOUND, "project not found")
        return project

    def artifact_path(self, project_id: str, relative_path: str) -> Any:
        root = (self.settings.data_dir / "artifacts" / project_id).resolve()
        candidate = (root / relative_path).resolve()
        if candidate != root and root not in candidate.parents:
            raise DashboardError(HTTPStatus.NOT_FOUND, "artifact not found")
        if not candidate.is_file():
            raise DashboardError(HTTPStatus.NOT_FOUND, "artifact not found")
        return candidate

    def public_workspace(self, payload: dict[str, Any], headers: Any) -> dict[str, Any]:
        """Return a browser-safe workspace view with a same-origin preview URL."""
        preview = payload.get("preview")
        if not isinstance(preview, dict):
            return payload
        if preview.get("status") == "RUNNING" and payload.get("project", {}).get("project_id"):
            project_id = str(payload["project"]["project_id"])
            forwarded = str(headers.get("X-Forwarded-Proto", "")).split(",", 1)[0].strip()
            scheme = forwarded if forwarded in {"http", "https"} else "http"
            host = str(headers.get("Host", f"127.0.0.1:{self.settings.dashboard_port}"))
            preview["url"] = f"{scheme}://{host}/api/projects/{quote(project_id, safe='')}/preview/"
        else:
            preview["url"] = None
        # The browser only needs the proxied URL and status. Keep local Docker
        # port/container details inside the trusted server process.
        preview["port"] = None
        preview["container_name"] = None
        return payload

    def handler(self) -> type[BaseHTTPRequestHandler]:
        app = self

        class Handler(BaseHTTPRequestHandler):
            def _token(self) -> str | None:
                cookie = SimpleCookie(self.headers.get("Cookie", ""))
                item = cookie.get("session")
                return item.value if item else None

            def _require(self, permission: Permission) -> tuple[Any, str]:
                try:
                    return app.auth.require(self._token(), permission)
                except AuthorizationDenied as error:
                    raise DashboardError(HTTPStatus.FORBIDDEN, str(error)) from error
                except AuthenticationError as error:
                    raise DashboardError(HTTPStatus.UNAUTHORIZED, str(error)) from error

            def _write_auth(self, permission: Permission) -> tuple[Any, str]:
                user, session_id = self._require(permission)
                try:
                    app.auth.require_csrf(session_id, self.headers.get("X-CSRF-Token"))
                except AuthenticationError as error:
                    raise DashboardError(HTTPStatus.FORBIDDEN, str(error)) from error
                return user, session_id

            def _body(self) -> dict[str, Any]:
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                except ValueError as error:
                    raise DashboardError(HTTPStatus.BAD_REQUEST, "invalid content length") from error
                if size < 0 or size > MAX_BODY_BYTES:
                    raise DashboardError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request body too large")
                try:
                    data = json.loads(self.rfile.read(size))
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise DashboardError(HTTPStatus.BAD_REQUEST, "invalid JSON") from error
                if not isinstance(data, dict):
                    raise DashboardError(HTTPStatus.BAD_REQUEST, "JSON object required")
                return data

            def _headers(self, content_type: str = "application/json") -> None:
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                    "frame-src 'self' http://127.0.0.1:*; connect-src 'self' http://127.0.0.1:*",
                )

            def _send(self, status: HTTPStatus, payload: Any, cookies: list[str] | None = None) -> None:
                body = json.dumps(payload, separators=(",", ":")).encode()
                self.send_response(status)
                self._headers()
                for cookie in cookies or []:
                    self.send_header("Set-Cookie", cookie)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _error(self, error: DashboardError) -> None:
                self._send(error.status, {"error": error.message})

            def _serve_preview(self, project_id: str, relative_parts: list[str]) -> None:
                if any(part in {"", ".", ".."} for part in relative_parts) or any(
                    "\x00" in part or "\\" in part for part in relative_parts
                ):
                    raise DashboardError(HTTPStatus.NOT_FOUND, "preview resource not found")
                session = app.workspace.preview.status(project_id)
                if session.status != "RUNNING" or session.port is None:
                    raise DashboardError(HTTPStatus.CONFLICT, "project preview is not running")
                target = "/" + "/".join(relative_parts) if relative_parts else "/"
                query = urlsplit(self.path).query
                if query:
                    target += "?" + query
                connection = http.client.HTTPConnection("127.0.0.1", session.port, timeout=10)
                try:
                    connection.request("GET", target, headers={"Accept": self.headers.get("Accept", "*/*")})
                    response = connection.getresponse()
                    body = response.read(MAX_PREVIEW_BYTES + 1)
                    if len(body) > MAX_PREVIEW_BYTES:
                        raise DashboardError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "preview response too large")
                    status = response.status
                    content_type = response.getheader("Content-Type", "application/octet-stream")
                except (OSError, TimeoutError) as error:
                    raise DashboardError(HTTPStatus.BAD_GATEWAY, "preview runtime is unavailable") from error
                finally:
                    connection.close()
                if "\r" in content_type or "\n" in content_type:
                    content_type = "application/octet-stream"
                prefix = "/api/projects/" + quote(project_id, safe="") + "/preview"
                if content_type.lower().startswith("text/html"):
                    body = _rewrite_preview_html(body, prefix)
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "SAMEORIGIN")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                    "script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'self'",
                )
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                try:
                    path = urlparse(self.path).path
                    if path == "/":
                        body = dashboard_html().encode()
                        self.send_response(HTTPStatus.OK)
                        self._headers("text/html; charset=utf-8")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                        return
                    if path == "/api/health":
                        self._send(HTTPStatus.OK, {"status": "ok"})
                        return
                    if path == "/api/auth/session":
                        user, session_id = self._require(Permission.READ)
                        self._send(HTTPStatus.OK, {"user": user.model_dump(mode="json"), "csrf": app.auth.rotate_csrf(session_id)})
                        return
                    if path == "/api/projects":
                        user, _ = self._require(Permission.READ)
                        records: list[dict[str, Any]] = []
                        pending: list[dict[str, Any]] = []
                        total_tokens = 0
                        for project in app.repository.list_projects_for_user(
                            user.user_id, admin=user.role is Role.ADMIN
                        ):
                            tasks = app.repository.list_tasks(project.project_id)
                            completed_tasks = sum(t.status.value == "COMPLETED" for t in tasks)
                            records.append({"project_id": project.project_id, "name": project.name, "status": project.status.value, "task_count": len(tasks), "completed_tasks": completed_tasks, "progress_percentage": round(completed_tasks / len(tasks) * 100) if tasks else 0, "active_tasks": sum(t.status.value in {"ASSIGNED", "IN_PROGRESS", "REVIEW"} for t in tasks)})
                            pending.extend(a.model_dump(mode="json") for a in app.repository.list_approvals(project.project_id) if a.decision.value == "PENDING")
                            total_tokens += app.repository.usage_summary(project.project_id)["total_tokens"]
                        self._send(HTTPStatus.OK, {"projects": records, "approvals_pending": len(pending), "total_tokens": total_tokens, "approvals": pending})
                        return
                    if path.startswith("/api/projects/"):
                        user, _ = self._require(Permission.READ)
                        path_parts = [unquote(part) for part in path.split("/") if part]
                        project_id = path_parts[2] if len(path_parts) > 2 else ""
                        app.project_for(user, project_id)
                        if len(path_parts) >= 4 and path_parts[3] == "preview":
                            self._serve_preview(project_id, path_parts[4:])
                            return
                        if len(path_parts) >= 4 and path_parts[3] == "artifacts":
                            relative_path = "/".join(path_parts[4:])
                            candidate = app.artifact_path(project_id, relative_path)
                            content = candidate.read_bytes()
                            if len(content) > 12 * 1024 * 1024:
                                raise DashboardError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "artifact too large")
                            content_type = "application/octet-stream"
                            if candidate.suffix.lower() == ".png":
                                content_type = "image/png"
                            elif candidate.suffix.lower() in {".json", ".html"}:
                                content_type = "application/json" if candidate.suffix.lower() == ".json" else "text/html; charset=utf-8"
                            self.send_response(HTTPStatus.OK)
                            self._headers(content_type)
                            self.send_header("Content-Length", str(len(content)))
                            self.end_headers()
                            self.wfile.write(content)
                            return
                        if len(path_parts) >= 4 and path_parts[3] == "workspace":
                            self._send(
                                HTTPStatus.OK,
                                app.public_workspace(app.workspace.workspace(project_id), self.headers),
                            )
                            return
                        if path.endswith("/metrics"):
                            self._send(HTTPStatus.OK, app.monitor.export(project_id))
                            return
                        project_record = app.project_for(user, project_id)
                        tasks = app.repository.list_tasks(project_id)
                        agents = app.repository.list_agents(project_id)
                        self._send(HTTPStatus.OK, {"project": project_record.model_dump(mode="json"), "tasks": [t.model_dump(mode="json") for t in tasks], "agents": [{"role": a.role, "status": a.status.value, "active": a.status.value in {"RUNNING", "ASSIGNED"}} for a in agents], "activity": app.repository.list_audit_events(project_id), "artifacts": app.repository.list_artifacts(project_id)})
                        return
                    raise DashboardError(HTTPStatus.NOT_FOUND, "route not found")
                except DashboardError as error:
                    self._error(error)
                except Exception:
                    LOGGER.exception("dashboard GET failed")
                    self._error(DashboardError(HTTPStatus.INTERNAL_SERVER_ERROR, "internal server error"))

            def do_POST(self) -> None:
                try:
                    path = urlparse(self.path).path
                    if path == "/api/auth/login":
                        data = self._body()
                        session = app.auth.login(str(data.get("username", "")), str(data.get("password", "")), self.client_address[0])
                        cookie = f"session={session.token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={app.settings.session_ttl_seconds}"
                        if app.settings.secure_cookie:
                            cookie += "; Secure"
                        self._send(HTTPStatus.OK, {"user": session.user.model_dump(mode="json"), "csrf": session.csrf_token}, [cookie])
                        return
                    if path == "/api/auth/logout":
                        app.auth.logout(self._token())
                        self._send(HTTPStatus.OK, {"status": "ok"}, ["session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"])
                        return
                    if path == "/api/projects":
                        user, _ = self._write_auth(Permission.CREATE_PROJECT)
                        project = app.orchestrator.create_project(ProjectRequest.model_validate(self._body()))
                        app.repository.add_project_member(project.project_id, user.user_id, "owner")
                        app.audit.record("PROJECT_MEMBER_ADDED", project_id=project.project_id, actor_id=user.user_id, payload={"role": "owner"})
                        self._send(HTTPStatus.CREATED, {"project": project.model_dump(mode="json")})
                        return
                    if path.startswith("/api/projects/") and path.endswith("/chat"):
                        user, _ = self._write_auth(Permission.OPERATE)
                        project_id = unquote(path.split("/")[3])
                        app.project_for(user, project_id)
                        data = self._body()
                        result = app.workspace.chat(project_id, user.user_id, str(data.get("content", "")))
                        self._send(HTTPStatus.OK, app.public_workspace(result, self.headers))
                        return
                    if path.startswith("/api/projects/") and path.endswith("/preview/start"):
                        user, _ = self._write_auth(Permission.OPERATE)
                        project_id = unquote(path.split("/")[3])
                        app.project_for(user, project_id)
                        data = self._body()
                        command = data.get("command")
                        if command is not None and (not isinstance(command, list) or not all(isinstance(item, str) for item in command)):
                            raise DashboardError(HTTPStatus.BAD_REQUEST, "command must be an argv list")
                        preview = app.workspace.preview.start(project_id, command)
                        payload = {"project": {"project_id": project_id}, "preview": preview.model_dump(mode="json")}
                        self._send(HTTPStatus.OK, app.public_workspace(payload, self.headers))
                        return
                    if path.startswith("/api/projects/") and path.endswith("/preview/stop"):
                        user, _ = self._write_auth(Permission.OPERATE)
                        project_id = unquote(path.split("/")[3])
                        app.project_for(user, project_id)
                        preview = app.workspace.preview.stop(project_id)
                        self._send(HTTPStatus.OK, {"preview": preview.model_dump(mode="json")})
                        return
                    if path.startswith("/api/approvals/") and path.endswith("/decision"):
                        user, _ = self._write_auth(Permission.APPROVE)
                        approval_id = path.split("/")[3]
                        approval = app.repository.get_approval(approval_id)
                        if approval is None:
                            raise DashboardError(HTTPStatus.NOT_FOUND, "approval not found")
                        data = self._body()
                        if data.get("decision") not in {"approve", "reject"}:
                            raise DashboardError(HTTPStatus.BAD_REQUEST, "decision must be approve or reject")
                        approved = data["decision"] == "approve"
                        reason = str(data.get("reason", ""))[:1000]
                        app.project_for(user, approval.project_id)
                        if approval.action == "approve_plan":
                            result = app.workspace.decide_approval(approval_id, user.user_id, approved, reason)
                            self._send(HTTPStatus.OK, app.public_workspace(result, self.headers))
                            return
                        else:
                            result = app.workspace.decide_approval(approval_id, user.user_id, approved, reason)
                            self._send(HTTPStatus.OK, app.public_workspace(result, self.headers))
                            return
                    raise DashboardError(HTTPStatus.NOT_FOUND, "route not found")
                except AuthenticationError as error:
                    self._error(DashboardError(HTTPStatus.UNAUTHORIZED, str(error)))
                except DashboardError as error:
                    self._error(error)
                except (ValueError, PreviewError) as error:
                    self._error(DashboardError(HTTPStatus.BAD_REQUEST, str(error)[:500]))
                except Exception:
                    LOGGER.exception("dashboard POST failed")
                    self._error(DashboardError(HTTPStatus.INTERNAL_SERVER_ERROR, "internal server error"))

            def do_DELETE(self) -> None:
                try:
                    path_parts = [unquote(part) for part in urlparse(self.path).path.split("/") if part]
                    if len(path_parts) != 3 or path_parts[:2] != ["api", "projects"]:
                        raise DashboardError(HTTPStatus.NOT_FOUND, "route not found")
                    user, _ = self._write_auth(Permission.DELETE_PROJECT)
                    project_id = path_parts[2]
                    app.project_for(user, project_id)
                    project_name = app.workspace.delete_project(project_id)
                    app.audit.record(
                        "PROJECT_DELETED",
                        project_id=project_id,
                        actor_id=user.user_id,
                        payload={"name": project_name},
                    )
                    self._send(
                        HTTPStatus.OK,
                        {"status": "deleted", "project_id": project_id, "name": project_name},
                    )
                except AuthenticationError as error:
                    self._error(DashboardError(HTTPStatus.UNAUTHORIZED, str(error)))
                except DashboardError as error:
                    self._error(error)
                except ProjectDeletionError as error:
                    self._error(DashboardError(HTTPStatus.CONFLICT, str(error)))
                except KeyError as error:
                    self._error(DashboardError(HTTPStatus.NOT_FOUND, f"project not found: {error.args[0]}"))
                except Exception:
                    LOGGER.exception("dashboard DELETE failed")
                    self._error(DashboardError(HTTPStatus.INTERNAL_SERVER_ERROR, "project deletion failed"))

            def log_message(self, format: str, *args: Any) -> None:
                LOGGER.info("dashboard request status=%s", args[1] if len(args) > 1 else "unknown")

        return Handler


def create_dashboard_server(settings: Settings, repository: Repository) -> ThreadingHTTPServer:
    app = DashboardApplication(settings, repository)
    app.bootstrap_admin(settings.dashboard_admin_username, settings.dashboard_admin_password)
    server = ThreadingHTTPServer((settings.dashboard_host, settings.dashboard_port), app.handler())
    # Keep the application lifecycle attached to the server so the dashboard
    # can release its bounded workflow executor during signal-driven shutdown.
    server._dashboard_application = app  # type: ignore[attr-defined]
    return server


def serve_dashboard(settings: Settings, repository: Repository) -> None:
    server = create_dashboard_server(settings, repository)

    def stop(_signum: int, _frame: Any) -> None:
        # signal handlers run on the serve_forever thread; shutdown() must be
        # called from another thread or Python's HTTP server can deadlock.
        threading.Thread(target=server.shutdown, name="dashboard-shutdown", daemon=True).start()

    old_term = signal.signal(signal.SIGTERM, stop)
    old_int = signal.signal(signal.SIGINT, stop)
    try:
        LOGGER.info("dashboard listening host=%s port=%d", settings.dashboard_host, server.server_port)
        server.serve_forever(poll_interval=0.25)
    finally:
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)
        server.server_close()
        application = getattr(server, "_dashboard_application", None)
        if isinstance(application, DashboardApplication):
            application.workspace.close()
