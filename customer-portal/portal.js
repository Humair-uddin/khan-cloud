const TOKEN="khan_cloud_token";
const $=id=>document.getElementById(id);
const token=()=>localStorage.getItem(TOKEN)||"";
const api=path=>path;
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
const bytes=n=>{
  if(!n)return "0 B";
  const u=["B","KiB","MiB","GiB","TiB"];
  let i=0,v=Number(n);
  while(v>=1024&&i<u.length-1){v/=1024;i++}
  return `${v.toFixed(i?1:0)} ${u[i]}`;
};
async function parse(r){
  const data=await r.json().catch(()=>({}));
  if(!r.ok)throw new Error(data.detail||`Request failed (${r.status})`);
  return data;
}
async function get(path){
  return parse(await fetch(api(path),{
    headers:{Authorization:`Bearer ${token()}`}
  }));
}
async function post(path,payload){
  return parse(await fetch(api(path),{
    method:"POST",
    headers:{
      Authorization:`Bearer ${token()}`,
      "Content-Type":"application/json"
    },
    body:JSON.stringify(payload)
  }));
}
function sshEndpoint(v){
  return (v.public_endpoints||[]).find(
    e=>
      e.protocol==="tcp"&&
      Number(e.private_port)===22&&
      e.status==="active"
  );
}
function endpointRows(v){
  const eps=v.public_endpoints||[];
  if(!eps.length){
    return `<div class="muted">No public endpoints assigned yet.</div>`;
  }
  return eps.map(e=>`
    <div>
      <strong>${esc(e.protocol.toUpperCase())}</strong>
      ${esc(e.public_ip)}:${e.public_port}
      <span class="muted">→ private port ${e.private_port}</span>
      <span class="status ${esc(e.status)}">
        ${esc(e.display_status||e.status)}
      </span>
    </div>
  `).join("");
}
async function refresh(){
  const s=await get("/api/v1/portal/summary");
  $("summary").innerHTML=[
    ["VPS",s.vps_total],
    ["Running",s.vps_running],
    ["Stopped",s.vps_stopped],
    ["Provisioning",s.vps_provisioning]
  ].map(x=>`<div class="stat"><small>${esc(x[0])}</small><strong>${x[1]}</strong></div>`).join("");
  $("count").textContent=s.vps_total;
  $("vps-list").innerHTML=s.vps.length?s.vps.map(v=>{
    const ssh=sshEndpoint(v);
    const sshText=ssh
      ? `ssh ${esc(v.access_username)}@${esc(ssh.public_ip)} -p ${ssh.public_port}`
      : "";
    return `<article class="vps">
      <div class="vps-top">
        <div>
          <strong>${esc(v.name)}</strong>
          <div class="muted">${esc(v.image)}</div>
        </div>
        <span class="status ${esc(v.status)}">${esc(v.status)}</span>
      </div>

      <div class="grid">
        <div><small>vCPU</small>${v.vcpu}</div>
        <div><small>Memory</small>${bytes(v.memory_bytes)}</div>
        <div><small>Disk</small>${bytes(v.disk_bytes)}</div>
        <div><small>Private IP</small>${esc(v.private_addresses[0]||v.primary_ip||"Pending")}</div>
      </div>

      <div class="access">
        <strong>Public endpoints</strong>
        <div>${endpointRows(v)}</div>
      </div>

      <div class="access">
        <strong>Secure access</strong>
        <div>${
          ssh
            ? `${sshText}<br><small class="muted">${esc(v.ssh_public_key_fingerprint)}</small>`
            : v.guest_ready_at
          ? (v.public_endpoints||[]).some(
              e=>
                e.protocol==="tcp"&&
                Number(e.private_port)===22
            )
            ? `SSH endpoint is being configured.<br><small class="muted">${esc(v.ssh_public_key_fingerprint)}</small>`
            : `SSH mapping not assigned yet.<br><small class="muted">${esc(v.ssh_public_key_fingerprint)}</small>`
          : "Preparing secure access…"
        }</div>
      </div>

      <div class="actions">
        <button class="secondary" data-id="${v.id}" data-action="start">Start</button>
        <button class="secondary" data-id="${v.id}" data-action="stop">Stop</button>
        <button class="secondary" data-id="${v.id}" data-action="reboot">Reboot</button>
        <button class="ghost" data-id="${v.id}" data-action="delete">Delete</button>
      </div>
    </article>`;
  }).join(""):`<div class="empty">No VPS services yet.</div>`;
}
$("login-form").addEventListener("submit",async e=>{
  e.preventDefault();
  const body=new URLSearchParams();
  body.set("username",$("username").value);
  body.set("password",$("password").value);
  try{
    const r=await fetch("/api/v1/auth/login",{
      method:"POST",
      headers:{"Content-Type":"application/x-www-form-urlencoded"},
      body
    });
    const d=await parse(r);
    localStorage.setItem(TOKEN,d.access_token);
    $("login").hidden=true;
    $("portal").hidden=false;
    await refresh();
  }catch(err){
    $("login-error").textContent=err.message;
  }
});
$("logout").addEventListener("click",()=>{
  localStorage.removeItem(TOKEN);
  location.reload();
});
$("vps-list").addEventListener("click",async e=>{
  const b=e.target.closest("button[data-action]");
  if(!b)return;
  b.disabled=true;
  try{
    await post(`/api/v1/compute/vps/${b.dataset.id}/actions`,{
      action:b.dataset.action
    });
    await refresh();
  }finally{
    b.disabled=false;
  }
});
get("/api/v1/auth/me")
  .then(u=>{
    $("user").textContent=u.username||u.email;
    $("login").hidden=true;
    $("portal").hidden=false;
    return refresh();
  })
  .catch(()=>localStorage.removeItem(TOKEN));

let currentQuote=null;
$("new-vps").addEventListener("click",async()=>{
  try{
    const c=await get("/api/v1/commerce/catalog");
    if(!c.length)throw new Error("VPS pricing has not been published yet.");
    $("order-modal").hidden=false;
  }catch(e){
    $("notice").textContent=e.message;
  }
});
$("close-order").addEventListener("click",()=>{
  $("order-modal").hidden=true;
});
$("quote-button").addEventListener("click",async()=>{
  try{
    currentQuote=await post("/api/v1/commerce/quotes/vps",{
      product_code:"vps-configurable",
      name:$("order-name").value.trim(),
      image:$("order-image").value,
      vcpu:Number($("order-cpu").value),
      memory_gib:Number($("order-ram").value),
      storage_gib:Number($("order-disk").value),
      network_tier:"shared_gateway",
      ssh_public_key:$("order-key").value.trim(),
      billing_period:"monthly"
    });
    $("quote-result").innerHTML=`<strong>Quote</strong><div>${esc(currentQuote.currency)} ${(currentQuote.amount_minor/100).toFixed(2)} / month</div>`;
    $("quote-result").hidden=false;
    $("place-order").disabled=false;
  }catch(e){
    $("order-error").textContent=e.message;
  }
});
$("order-form").addEventListener("submit",async e=>{
  e.preventDefault();
  if(!currentQuote)return;
  try{
    const o=await post("/api/v1/commerce/orders",{
      quote_id:currentQuote.id,
      payment_method:$("payment-method").value
    });
    $("order-modal").hidden=true;
    $("notice").textContent=`Order ${o.id} created. Status: ${o.status}. Payment confirmation is required before provisioning.`;
  }catch(err){
    $("order-error").textContent=err.message;
  }
});
