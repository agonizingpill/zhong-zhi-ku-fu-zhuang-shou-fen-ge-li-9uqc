from sqlalchemy import select,func
from .db import Base,engine,Session
from .models import *
from .auth import hashed

def seed():
    Base.metadata.create_all(engine)
    with Session() as s:
        for role in ('operator','supervisor','viewer'):
            email=role+'@qinghe.demo'
            if not s.scalar(select(User).where(User.email==email)):s.add(User(email=email,role=role,password_hash=hashed('Seeds2026!')))
        a=s.scalar(select(Accession).where(Accession.code=='QH-021'))
        if not a:a=Accession(code='QH-021',crop='青豆',name='青禾早熟青豆',origin='青禾北圃2023采集',minimum=300);s.add(a);s.flush()
        for code,generation,available in [('QH-021-G3',3,960),('QH-021-POLLEN',3,400)]:
            if not s.scalar(select(Lot).where(Lot.code==code)):s.add(Lot(accession_id=a.id,code=code,generation=generation,available=available,stored_months=36,temperature=4,initial_rate=94))
        other=s.scalar(select(Accession).where(Accession.code=='QH-087'))
        if not other:other=Accession(code='QH-087',crop='青豆',name='异源晚熟青豆',origin='南坡异源对照',minimum=300);s.add(other);s.flush()
        if not s.scalar(select(Lot).where(Lot.code=='QH-087-G2')):s.add(Lot(accession_id=other.id,code='QH-087-G2',generation=2,available=800,stored_months=18,temperature=-8,initial_rate=96))
        qh90=s.scalar(select(Accession).where(Accession.code=='QH-090'))
        if not qh90:qh90=Accession(code='QH-090',crop='青豆',name='南坡晚熟青豆',origin='南坡2024采集',minimum=300);s.add(qh90);s.flush()
        # 历史收货单：主管已核实的同源/异源记录，供名称与来源匹配学习。
        for code,bag,name,origin,seeds,verdict,acc in [('RC-SEED-01','BAG-2023-07','青禾早熟青豆','青禾北圃2023采集补份',200,'homologous',a),('RC-SEED-02','BAG-2024-11','南坡晚熟青豆','南坡2024采集',300,'heterologous',qh90),('RC-SEED-03','BAG-2024-02','异源晚熟青豆','南坡异源对照补采',150,'homologous',other)]:
            if not s.scalar(select(Receipt).where(Receipt.code==code)):
                lot0=s.scalar(select(Lot).where(Lot.code==code+'-RC'))
                if not lot0:lot0=Lot(accession_id=acc.id,code=code+'-RC',generation=0,available=seeds,stored_months=0,temperature=-18,initial_rate=0);s.add(lot0);s.flush()
                s.add(Receipt(code=code,bag_code=bag,crop='青豆',name=name,origin=origin,seeds=seeds,state=verdict,snapshot=0,accession_id=acc.id,lot_id=lot0.id))
        for i in range(18):
            code=chr(65+i//6)+str(i%6+1)
            if not s.scalar(select(Plot).where(Plot.code==code)):s.add(Plot(code=code,row=i//6,position=i%6,capacity=250))
        s.flush();lot=s.scalar(select(Lot).where(Lot.code=='QH-021-G3'))
        if not s.scalar(select(GerminationTest).where(GerminationTest.code=='GT-SEED-80')):s.add(GerminationTest(lot_id=lot.id,code='GT-SEED-80',sampled=100,germinated=80,state='recorded'))
        s.commit();return {cls.__tablename__:s.scalar(select(func.count()).select_from(cls))for cls in (User,Accession,Lot,GerminationTest,Regeneration,Plot,Flowering,Pollination,Harvest,Distribution,Receipt)}
