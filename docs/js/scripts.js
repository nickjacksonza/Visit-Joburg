(function(){
if(!window.__analytics)return;
var KEY='consent-v1';
var saved=null;
try{saved=localStorage.getItem(KEY);}catch(e){}
function apply(v){
gtag('consent','update',{analytics_storage:v});
if(v==='granted'&&window.__loadGtag)window.__loadGtag();
try{localStorage.setItem(KEY,v);}catch(e){}
}
if(saved)return apply(saved);
var b=document.createElement('div');
b.className='pr-consent';
b.setAttribute('role','region');
b.setAttribute('aria-label','Cookie consent');
b.innerHTML='<p>Analytics cookies stay off unless you accept. If you decline, at most anonymous, cookieless counts are sent.</p><button class="btn" id="c-y">Accept</button><button class="btn" id="c-n">Decline</button>';
document.body.appendChild(b);
b.querySelector('#c-y').onclick=function(){apply('granted');b.remove();};
b.querySelector('#c-n').onclick=function(){apply('denied');b.remove();};
})();
(function(){
var btn=document.querySelector('.nav-toggle'),nav=document.getElementById('site-nav');
if(!btn||!nav)return;
function set(open){
btn.setAttribute('aria-expanded',String(open));
btn.textContent=open?'Close':'Menu';
nav.classList.toggle('open',open);
document.body.classList.toggle('nav-open',open);
if(open)nav.querySelector('a').focus();
}
btn.addEventListener('click',function(){set(btn.getAttribute('aria-expanded')!=='true');});
document.addEventListener('keydown',function(e){
if(btn.getAttribute('aria-expanded')!=='true')return;
if(e.key==='Escape'){set(false);btn.focus();}
if(e.key==='Tab'){
var items=[btn].concat([].slice.call(nav.querySelectorAll('a')));
var i=items.indexOf(document.activeElement);
if(e.shiftKey&&i<=0){e.preventDefault();items[items.length-1].focus();}
else if(!e.shiftKey&&i===items.length-1){e.preventDefault();items[0].focus();}
}
});
})();
