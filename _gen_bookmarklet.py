"""Gera o bookmarklet e injeta no HTML."""
import urllib.parse

JS = r"""(function(){
var r=document.querySelectorAll('.market_history_row');
if(!r.length){alert('Va em steamcommunity.com/market > My History primeiro.');return;}
var c='# Steam Market History - SkinVault\n';
r.forEach(function(x){
var n=x.querySelector('.market_listing_item_name');
if(!n)return;
var name=n.textContent.trim();
var p=x.querySelector('.market_history_price');
var price=p?p.textContent.trim():'0';
var q=x.querySelector('.market_history_quantity,.market_history_amount');
var qty=q?parseInt(q.textContent.replace(/[^0-9]/g,'')||1):1;
c+=name+', '+price+', '+qty+'\n';
});
var d=document.createElement('div');
d.style.cssText='position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.75);z-index:99999;display:flex;align-items:center;justify-content:center;font-family:Segoe UI,sans-serif;';
d.innerHTML='<div style="background:#0E0E12;color:#E6E6EA;padding:24px;border-radius:12px;max-width:680px;width:90%;max-height:80vh;overflow:auto;">'+
'<h3 style="margin:0 0 4px;color:#22C55E;font-size:16px;">SkinVault - Dados extraidos</h3>'+
'<p style="color:#9D9DA8;font-size:12px;margin:0 0 12px;">Copie e cole no Importar CSV do SkinVault.</p>'+
'<textarea id="svc" style="width:100%;height:260px;background:#16161C;color:#E6E6EA;border:1px solid #2A2A33;border-radius:8px;padding:12px;font-size:11px;font-family:monospace;box-sizing:border-box;">'+c+'</textarea>'+
'<div style="margin-top:12px;display:flex;gap:8px;">'+
'<button onclick="var t=document.getElementById(\'svc\');t.select();navigator.clipboard.writeText(t.value).catch(function(){t.select();document.execCommand(\'copy\');});this.textContent=\'Copiado!\'" style="padding:10px 22px;background:rgba(34,197,94,0.16);color:#DCFFE6;border:1px solid #22C55E;border-radius:8px;cursor:pointer;font-size:11pt;font-weight:600;">Copiar</button>'+
'<button onclick="this.parentElement.parentElement.parentElement.remove()" style="padding:10px 22px;background:rgba(255,255,255,0.06);color:#E6E6EA;border:1px solid #3A3A44;border-radius:8px;cursor:pointer;font-size:11pt;font-weight:600;">Fechar</button>'+
'<span style="color:#9D9DA8;font-size:11px;margin-left:12px;align-self:center;">'+c.split('\n').filter(function(l){return l&&!l.startsWith('#')}).length+' itens</span>'+
'</div></div>';
document.body.appendChild(d);
})()"""

encoded = 'javascript:' + urllib.parse.quote(JS, safe='=?')

html = open('bookmarklet.html', encoding='utf-8').read()
html = html.replace('JAVASCRIPT_PLACEHOLDER', encoded)
open('bookmarklet.html', 'w', encoding='utf-8').write(html)

print(f'Bookmarklet gerado ({len(encoded)} chars)')
print(f'Abrir bookmarklet.html no navegador e arrastar o link para a barra de favoritos.')
