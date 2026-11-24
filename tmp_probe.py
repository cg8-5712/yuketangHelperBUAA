from yuketang_helper.platform.client import PlatformClient
from yuketang_helper.platform.video import VideoAPI
import time, random
domain='aibuaa.yuketang.cn'; uv=3832
headers={'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36','Content-Type':'application/json','Cookie':'csrftoken=5aGUMgOAnhWOY6AVC24wwItRZYeqsecU; sessionid=f07lowlhe2uku84546pnf3c4dx3r3ema; university_id=3832; platform_id=3','x-csrftoken':'5aGUMgOAnhWOY6AVC24wwItRZYeqsecU','university-id':'3832','xtbz':'cloud'}
c=PlatformClient(domain,uv,headers); v=VideoAPI(c)
cid=3447587; uid=64024722; classroom=26845551; vid=49517022; sku=13285017
ccid='CAE5D773CC92139BFC9558351D509E7C'; d=519.403
p=v.progress(cid,uid,classroom,vid); base=float(p['watch_length']); print('before',p)
pg=f'{vid}_'+''.join(random.sample('abcdefghijklmnopqrstuvwxyz0123456789',5))
def hb(ts,sq,et,cp,tp):
    return {"i":5,"et":et,"p":"web","n":"ali-cdn.xuetangx.com","lob":"cloud4","cp":round(cp,1),"fp":0,"tp":round(tp,1),"sp":1,"ts":str(ts),"u":uid,"uip":"","c":cid,"v":vid,"skuid":sku,"classroomid":str(classroom),"cc":ccid,"d":0 if et=="loadstart" else round(d,1),"pg":pg,"sq":sq,"t":"video","cards_id":0,"slide":0,"v_url":""}
now=int(time.time()*1000)
payload={"heart_data":[
 hb(now,1,'loadstart',base,0),
 hb(now+300,2,'play',base,base),
 hb(now+400,3,'playing',base,base),
 hb(now+5400,4,'heartbeat',base+4.9,base),
]}
r=v.heartbeat(payload); print('resp',r[:300])
print('after',v.progress(cid,uid,classroom,vid))
