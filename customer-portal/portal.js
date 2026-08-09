const TOKEN="kc_customer_token";
const $=(id)=>document.getElementById(id);
const api=(path)=>path;

async function parse(r){
  const body=(r.headers.get("content-type")||"").includes("json")?await r.json():await r.text();
  if(!r.ok) throw new Error(body?.detail||body||`Request failed ${r.status}`);
  return body;
}
function token(){return localStorage.getItem(TOKEN)||""}
async function get(path){return parse(await fetch(api(path),{headers:{Authorization:`Bearer ${token()}`}}))}
async function post(path,payload){return parse(await fetch(api(path),{method:"POST",headers:{Authorization:`Bearer ${token()}`,"Content-Type":"application/json"},body:JSON.stringify(payload)}))}
function bytes(n){n=Number(n||0);if(n>=1073741824)return `${(n/1073741824).toFixed(1)} GiB`;return `${Math.round(n/1048576)} MiB`}
function esc(v){return String(v??"").replace(/[&<>'"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]))}

async function refresh(){
  const s=await get("/api/v1/portal/summary");
  $("summary").innerHTML=[
    ["VPS",s.vps_total],["Running",s.vps_running],["Stopped",s.vps_stopped],["Provisioning",s.vps_provisioning]
  ].map(([k,v])=>`<article class="stat"><small>${k}</small><strong>${v}</strong></article>`).join("");
  $("count").textContent=s.vps_total;
  $("vps-list").innerHTML=s.vps.length?s.vps.map(v=>`<article class="vps">
    <div class="vps-top"><div><strong>${esc(v.name)}</strong><div class="muted">${esc(v.image)}</div></div><span class="status ${esc(v.status)}">${esc(v.status)}</span></div>
    <div class="grid"><div><small>vCPU</small>${v.vcpu}</div><div><small>Memory</small>${bytes(v.memory_bytes)}</div><div><small>Disk</small>${bytes(v.disk_bytes)}</div><div><small>Private IP</small>${esc(v.private_addresses[0]||v.primary_ip||"Pending")}</div></div>
    <div class="access"><strong>Secure access</strong><div>${v.guest_ready_at?`SSH ${esc(v.access_username)}@${esc(v.primary_ip)}<br><small class="muted">${esc(v.ssh_public_key_fingerprint)}</small>`:"Preparing secure access…"}</div></div>
    <div class="actions">
      ${v.status==="running"?`<button data-id="${v.id}" data-action="stop" class="secondary">Stop</button><button data-id="${v.id}" data-action="reboot" class="secondary">Reboot</button>`:""}
      ${v.status==="stopped"?`<button data-id="${v.id}" data-action="start">Start</button>`:""}
      ${!["deleted","provisioning"].includes(v.status)?`<button data-id="${v.id}" data-action="delete" class="ghost">Delete</button>`:""}
    </div>
  </article>`).join(""):`<div class="empty">No VPS services yet.</div>`;
}

$("login-form").addEventListener("submit",async e=>{
  e.preventDefault();$("login-error").textContent="";
  try{
    const body=new URLSearchParams({username:$("username").value,password:$("password").value});
    const r=await fetch("/api/v1/auth/login",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body});
    const data=await parse(r);localStorage.setItem(TOKEN,data.access_token);$("user").textContent=data.user?.username||data.user?.email||"Account";
    $("login").hidden=true;$("portal").hidden=false;await refresh();
  }catch(err){$("login-error").textContent=err.message}
});
$("vps-list").addEventListener("click",async e=>{
  const b=e.target.closest("button[data-action]");if(!b)return;b.disabled=true;
  try{await post(`/api/v1/compute/vps/${b.dataset.id}/actions`,{action:b.dataset.action});await refresh()}finally{b.disabled=false}
});
$("refresh").addEventListener("click",refresh);
$("logout").addEventListener("click",()=>{localStorage.removeItem(TOKEN);location.reload()});

if(token()){
  get("/api/v1/auth/me").then(u=>{$("user").textContent=u.username||u.email;$("login").hidden=true;$("portal").hidden=false;return refresh()}).catch(()=>localStorage.removeItem(TOKEN));
}

let currentQuote=null;
$("new-vps").addEventListener("click",async()=>{try{const c=await get("/api/v1/commerce/catalog");if(!c.length)throw new Error("VPS pricing has not been published yet.");$("order-modal").hidden=false}catch(e){$("notice").textContent=e.message}});
$("close-order").addEventListener("click",()=>{$("order-modal").hidden=true});
$("quote-button").addEventListener("click",async()=>{try{currentQuote=await post("/api/v1/commerce/quotes/vps",{product_code:"vps-configurable",name:$("order-name").value.trim(),image:$("order-image").value,vcpu:Number($("order-cpu").value),memory_gib:Number($("order-ram").value),storage_gib:Number($("order-disk").value),network_tier:"shared_gateway",ssh_public_key:$("order-key").value.trim(),billing_period:"monthly"});$("quote-result").innerHTML=`<strong>Quote</strong><div>${esc(currentQuote.currency)} ${(currentQuote.amount_minor/100).toFixed(2)} / month</div>`;$("quote-result").hidden=false;$("place-order").disabled=false}catch(e){$("order-error").textContent=e.message}});
$("order-form").addEventListener("submit",async e=>{e.preventDefault();if(!currentQuote)return;try{const o=await post("/api/v1/commerce/orders",{quote_id:currentQuote.id,payment_method:$("payment-method").value});$("order-modal").hidden=true;$("notice").textContent=`Order ${o.id} created. Status: ${o.status}. Payment confirmation is required before provisioning.`}catch(err){$("order-error").textContent=err.message}});
