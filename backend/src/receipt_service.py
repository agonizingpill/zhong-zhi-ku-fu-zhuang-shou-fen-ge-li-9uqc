import difflib
from sqlalchemy import select,func
from fastapi import HTTPException
from .models import Accession,Lot,Receipt
from .common import lock,pack,add,audit

def sim(a,b):
    norm=lambda x:''.join(c for c in str(x).lower() if c.isalnum())
    return round(difflib.SequenceMatcher(None,norm(a),norm(b)).ratio(),4)

def verified_pairs(s):
    # 主管已核实记录：同源单与所挂旧档为正例；异源单与除自建新档外的旧档为反例。
    accessions=s.scalars(select(Accession)).all();out=[]
    for r in s.scalars(select(Receipt).where(Receipt.state!='pending')).all():
        for a in accessions:
            if a.crop!=r.crop:continue
            if r.state=='homologous':
                if a.id==r.accession_id:out.append((sim(r.name,a.name),sim(r.origin,a.origin),True))
            elif a.id!=r.accession_id:out.append((sim(r.name,a.name),sim(r.origin,a.origin),False))
    return out

def learn(s):
    # 网格搜索可复现：正确数优先，再少漏同源、少误判，权重并列取均衡、阈值并列取低。
    data=verified_pairs(s)
    pos=sum(1 for _,_,p in data if p);neg=len(data)-pos
    if pos<2 or neg<2:return {'w_name':0.5,'w_origin':0.5,'threshold':0.6,'learned':False,'positives':pos,'negatives':neg}
    best=None
    for i in range(11):
        w=round(i*0.1,1)
        for j in range(30,96,5):
            t=j/100;tp=fn=fp=tn=0
            for ns,os_,p in data:
                hit=w*ns+(1-w)*os_>=t
                if p and hit:tp+=1
                elif p:fn+=1
                elif hit:fp+=1
                else:tn+=1
            key=(tp+tn,-fn,-fp,-abs(w-0.5))
            if best is None or key>best[0]:best=(key,w,t)
    _,w,t=best
    return {'w_name':w,'w_origin':round(1-w,1),'threshold':t,'learned':True,'positives':pos,'negatives':neg}

def candidates(s,receipt,model):
    out=[]
    for a in s.scalars(select(Accession).where(Accession.crop==receipt.crop)).all():
        ns,os_=sim(receipt.name,a.name),sim(receipt.origin,a.origin)
        score=round(model['w_name']*ns+model['w_origin']*os_,4)
        out.append({'accession_id':a.id,'code':a.code,'name':a.name,'origin':a.origin,'name_sim':ns,'origin_sim':os_,'score':score,'match':score>=model['threshold']})
    out.sort(key=lambda c:(-c['score'],c['accession_id']))
    return out

def recommendations(s):
    model=learn(s)
    pending=s.scalars(select(Receipt).where(Receipt.state=='pending').order_by(Receipt.id)).all()
    return {'model':model,'pending':[{'receipt_id':r.id,'candidates':candidates(s,r,model)[:5]} for r in pending]}

def register(s,d,u):
    # 高水位快照：并发建档判定以此重比后到的种质。
    high=s.scalar(select(func.coalesce(func.max(Accession.id),0)))
    x=Receipt(**d.model_dump(),snapshot=high)
    audit(s,u,'登记收货单 '+d.code+' 待核对 '+str(d.seeds)+'粒')
    return add(s,x)

def judge(s,id,d,u):
    r=lock(s,Receipt,id)
    if r.state!='pending':raise HTTPException(409,'收货单已判定入库，重试不会重复建批')
    if d.verdict=='homologous':
        if d.accession_id is None:raise HTTPException(422,'判同源需指定挂靠的旧档')
        a=lock(s,Accession,d.accession_id)
        if a.crop!=r.crop:raise HTTPException(409,'作物不一致，不能挂靠该旧档')
        lot=Lot(accession_id=a.id,code=r.code+'-RC',generation=0,available=r.seeds,stored_months=0,temperature=-18,initial_rate=0)
        s.add(lot);s.flush()
        r.state='homologous';r.accession_id=a.id;r.lot_id=lot.id
        audit(s,u,'主管判同源 '+r.code+' 实收'+str(r.seeds)+'粒挂入 '+a.code)
        return pack(r)
    if not d.new_code:raise HTTPException(422,'判异源需给定新种质号')
    # 锁全部种质行串行建档；把登记高水位之后先入的种质纳入重比。
    s.scalars(select(Accession.id).order_by(Accession.id).with_for_update()).all()
    model=learn(s)
    fresh=[c for c in candidates(s,r,model) if c['match'] and c['accession_id']>r.snapshot]
    if fresh:
        r.snapshot=s.scalar(select(func.coalesce(func.max(Accession.id),0)))
        r.recheck={'candidates':fresh[:5],'model':model}
        s.commit()
        raise HTTPException(409,'登记后新入藏种质 '+','.join(c['code'] for c in fresh)+' 与本袋相似，已纳入重比，请复核后再定')
    a=Accession(code=d.new_code,crop=r.crop,name=r.name,origin=r.origin,minimum=d.minimum)
    s.add(a);s.flush()
    lot=Lot(accession_id=a.id,code=r.code+'-RC',generation=0,available=r.seeds,stored_months=0,temperature=-18,initial_rate=0)
    s.add(lot);s.flush()
    r.state='heterologous';r.accession_id=a.id;r.lot_id=lot.id
    audit(s,u,'主管判异源 '+r.code+' 建新档 '+a.code+' 实收'+str(r.seeds)+'粒')
    return pack(r)
