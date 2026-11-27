(function(){
var sel=document.getElementById('map-area'),fig=document.getElementById('map'),info=document.getElementById('map-info'),
out=document.getElementById('map-out');
if(!sel||!fig||!info||!window.fetch||!window.DOMParser)return;
var NS='http://www.w3.org/2000/svg',SLICES=8,svg=null,loading=null,region=null,full=null,view=null,anim=0,
still=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;
function load(){
if(loading)return loading;
var img=fig.querySelector('img'),base=img.getAttribute('src').replace(/[^/]*$/,'');
var map=fetch(img.getAttribute('src')).then(function(r){return r.text();}).then(function(t){
var doc=new DOMParser().parseFromString(t,'image/svg+xml');
svg=document.importNode(doc.documentElement,true);
svg.removeAttribute('width');
svg.removeAttribute('height');
svg.setAttribute('class','map-svg');
svg.setAttribute('aria-label',img.getAttribute('alt'));
full=svg.getAttribute('viewBox').split(/\s+/).map(Number);
view=full.slice();
var fine=document.createElementNS(NS,'g');
fine.id='fine';
var hexes=svg.getElementById('hexes');
hexes.parentNode.insertBefore(fine,hexes.nextSibling);
fig.replaceChild(svg,img);
svg.addEventListener('click',onTap);
});
var reg=fetch(base+'region.json').then(function(r){return r.json();}).then(function(d){region=d;},function(){});
loading=Promise.all([map,reg]);
return loading;
}
function setView(v){
view=v;
svg.setAttribute('viewBox',v.map(function(n){return n.toFixed(2);}).join(' '));
svg.style.setProperty('--z',(v[2]/full[2]).toFixed(4));
svg.classList.toggle('zoomed',v[2]<full[2]*0.95);
}
function zoomTo(v,done){
cancelAnimationFrame(anim);
if(still){setView(v);if(done)done();return;}
var from=view.slice(),t0=performance.now(),T=700;
(function step(now){
var t=Math.min(1,(now-t0)/T),e=t<.5?2*t*t:1-Math.pow(-2*t+2,2)/2;
setView(from.map(function(a,i){return a+(v[i]-a)*e;}));
if(t<1)anim=requestAnimationFrame(step);else if(done)done();
})(t0);
}
function frame(box){
var a=full[2]/full[3],w=Math.max(box.width*2.4,70),h=Math.max(box.height*2.4,70);
if(w/h>a)h=w/a;else w=h*a;
var cx=box.x+box.width/2,cy=box.y+box.height/2-h*0.08;
return[cx-w/2,cy-h/2,w,h];
}
function hexD(x,y,r){
var d='';
for(var k=0;k<6;k++){
var t=Math.PI/180*(30+60*k);
d+=(k?'L':'M')+(x+r*Math.cos(t)).toFixed(1)+','+(y+r*Math.sin(t)).toFixed(1);
}
return d+'Z';
}
function fineGroup(id){
var g=svg.getElementById('fine-'+id);
if(g||!region||!region.areas[id])return g;
g=document.createElementNS(NS,'g');
g.id='fine-'+id;
region.areas[id].forEach(function(c){
var p=document.createElementNS(NS,'path');
p.setAttribute('d',hexD(c[0],c[1],region.r));
p.setAttribute('fill','#'+c[2]);
g.appendChild(p);
});
svg.getElementById('fine').appendChild(g);
return g;
}
function showFine(v){
if(!region)return false;
Object.keys(region.areas).forEach(function(id){
var b=region.box||(region.box={}),cs=region.areas[id];
if(!b[id]){
var xs=cs.map(function(c){return c[0];}),ys=cs.map(function(c){return c[1];});
b[id]=[Math.min.apply(0,xs),Math.min.apply(0,ys),Math.max.apply(0,xs),Math.max.apply(0,ys)];
}
var q=b[id];
if(q[2]>=v[0]&&q[0]<=v[0]+v[2]&&q[3]>=v[1]&&q[1]<=v[1]+v[3])fineGroup(id);
});
svg.classList.add('fine');
return true;
}
function clear(){
var old=svg.querySelector('.lift');
if(old)old.parentNode.removeChild(old);
[].forEach.call(svg.querySelectorAll('.picked'),function(n){n.classList.remove('picked');});
svg.classList.remove('picking');
}
function centreY(d){
var n=d.match(/-?\d+(\.\d+)?/g).map(Number),y=0;
for(var i=1;i<n.length;i+=2)y+=n[i];
return y/(n.length/2);
}
function lift(groups,name,share){
var cells=[];
groups.forEach(function(grp){
[].forEach.call(grp.querySelectorAll('path'),function(p){
var d=p.getAttribute('d');
cells.push({d:d,y:centreY(d)});
});
});
cells.sort(function(a,b){return a.y-b.y;});
var n=cells.length>300?4:SLICES,height=view[3]*share;
var g=document.createElementNS(NS,'g');
g.setAttribute('class','lift');
g.style.setProperty('--step',(height/n).toFixed(2)+'px');
cells.forEach(function(c){
for(var k=1;k<=n;k++){
var s=document.createElementNS(NS,'path');
s.setAttribute('d',c.d);
s.setAttribute('class','slice k'+k+(k===n?' top':''));
g.appendChild(s);
}
});
var x0=Infinity,x1=-Infinity,y0=Infinity;
groups.forEach(function(grp){
var b=grp.getBBox();
x0=Math.min(x0,b.x);x1=Math.max(x1,b.x+b.width);y0=Math.min(y0,b.y);
});
var l=document.createElementNS(NS,'text');
l.setAttribute('class','lift-label');
l.setAttribute('x',(x0+x1)/2);
l.setAttribute('y',y0-height-8*view[2]/full[2]);
l.setAttribute('text-anchor','middle');
l.setAttribute('font-size','13');
l.setAttribute('font-weight','700');
l.setAttribute('font-family','Inter, Arial, sans-serif');
l.setAttribute('stroke-width','3');
l.setAttribute('paint-order','stroke');
l.textContent=name;
g.appendChild(l);
svg.appendChild(g);
requestAnimationFrame(function(){requestAnimationFrame(function(){g.classList.add('up');});});
}
function pickRegion(rid){
clear();
svg.classList.remove('fine');
var opts=[].slice.call(sel.querySelectorAll('option[data-region="'+rid+'"]'));
var groups=opts.map(function(o){return svg.getElementById('hex-'+o.value);}).filter(Boolean);
if(!groups.length)return;
out.hidden=false;
svg.classList.add('picking');
groups.forEach(function(g){g.classList.add('picked');});
var name=sel.options[sel.selectedIndex].getAttribute('data-name');
info.textContent='';
var h=document.createElement('h3'),p=document.createElement('p');
h.textContent=name;
p.textContent=groups.length+' suburbs on the map: '+opts.map(function(o){return o.textContent;}).join(', ')+'. Pick one to zoom in.';
info.appendChild(h);
info.appendChild(p);
zoomTo(full.slice(),function(){lift(groups,name,0.05);});
}
function pick(id){
if(id&&id.indexOf('all:')===0)return pickRegion(id.slice(4));
clear();
var city=id&&svg.getElementById('hex-'+id);
if(!city){info.textContent='';whole();return;}
out.hidden=false;
svg.classList.add('picking');
city.classList.add('picked');
var outline=svg.getElementById(id);
if(outline)outline.classList.add('picked');
show(sel.options[sel.selectedIndex]);
var target=frame(city.getBBox());
zoomTo(target,function(){
var grp=showFine(target)&&fineGroup(id);
if(grp)grp.classList.add('picked');
lift([grp||city],sel.options[sel.selectedIndex].textContent,0.1);
});
}
function whole(){
if(!svg)return;
clear();
svg.classList.remove('fine');
out.hidden=true;
zoomTo(full.slice());
}
function show(opt){
info.textContent='';
if(!opt||!opt.value)return;
var h=document.createElement('h3'),p=document.createElement('p');
h.textContent=opt.textContent;
p.textContent=opt.getAttribute('data-summary')||'We have not written up this area yet.';
info.appendChild(h);
info.appendChild(p);
if(opt.getAttribute('data-href')){
var a=document.createElement('a'),q=document.createElement('p');
a.href=opt.getAttribute('data-href');
a.textContent='Read the '+opt.textContent+' guide';
q.appendChild(a);
info.appendChild(q);
}
}
function onTap(e){
var g=e.target.closest('[id^="hex-"], [id^="fine-"]');
var id=g?g.id.replace(/^(hex|fine)-/,''):null;
if(!id){
var a=e.target.closest('#areas > *');
id=a?a.id:null;
}
if(!id||!sel.querySelector('option[value="'+id+'"]'))return;
sel.value=id;
pick(id);
}
sel.addEventListener('focus',load);
sel.addEventListener('change',function(){load().then(function(){pick(sel.value);});});
out.addEventListener('click',function(){sel.value='';info.textContent='';whole();sel.focus();});
fig.addEventListener('click',function(){if(!svg)load();});
})();
