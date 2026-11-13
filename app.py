'''성실한 다민이가 될꺼에요! — streamlit run app.py
Python 3.11+. 배포·저장·보안 안내는 앱의 '설정·도움말' 참조.
'''
import os
import io
import json
import hmac
import hashlib
import secrets
import sqlite3
import calendar
import tempfile
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import streamlit as st
import pandas as pd
import qrcode

st.set_page_config(page_title="성실한 다민이가 될꺼에요!", page_icon="🌱", layout="centered")
TZ=ZoneInfo('Asia/Seoul')
def now(): return datetime.now(TZ).isoformat(timespec='seconds')
def today(): return datetime.now(TZ).date()
def secret(key, default=''):
    try: return st.secrets.get(key, os.environ.get(key, default))
    except Exception: return os.environ.get(key, default)
# 체험마다 별도 임시 DB를 사용하며 실제 가족 DB는 읽거나 수정하지 않습니다.
if st.session_state.get('demo_mode'):
    if 'demo_storage' not in st.session_state:
        st.session_state['demo_storage']=tempfile.TemporaryDirectory(prefix='damin-demo-')
    DB=os.path.join(st.session_state['demo_storage'].name,'demo.sqlite3')
else:
    DB=secret('DB_PATH','damin.sqlite3')
def conn():
    c=sqlite3.connect(DB,timeout=30)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c
with conn() as c:
    c.executescript('''CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS quests(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,description TEXT NOT NULL,due TEXT,status TEXT NOT NULL DEFAULT 'open',created TEXT NOT NULL,submitted TEXT,approved TEXT,note TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS members(quest_id INTEGER NOT NULL REFERENCES quests(id),name TEXT NOT NULL,reward INTEGER NOT NULL CHECK(reward>=0),done INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(quest_id,name));
    CREATE TABLE IF NOT EXISTS payouts(id INTEGER PRIMARY KEY AUTOINCREMENT,paid_at TEXT NOT NULL,total INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS ledger(id INTEGER PRIMARY KEY AUTOINCREMENT,quest_id INTEGER NOT NULL REFERENCES quests(id),name TEXT NOT NULL,amount INTEGER NOT NULL,earned TEXT NOT NULL,payout_id INTEGER REFERENCES payouts(id),UNIQUE(quest_id,name));''')
def setting(key, default=''):
    with conn() as c: r=c.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
    return r['value'] if r else default
def put(c,key,value): c.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,str(value)))
def digest(pin,salt): return hashlib.pbkdf2_hmac('sha256',pin.encode(),bytes.fromhex(salt),310000).hex()
def set_pin(c,key,pin):
    salt=secrets.token_hex(16); put(c,key,json.dumps({'salt':salt,'hash':digest(pin,salt)}))
def check_pin(key,pin):
    try:
        v=json.loads(setting(key)); return hmac.compare_digest(v['hash'],digest(pin,v['salt']))
    except Exception: return False
def query(sql,args=()):
    with conn() as c: return [dict(r) for r in c.execute(sql,args).fetchall()]
def money(n): return f'{int(n):,}원'
def next_date(start,period):
    d=date.fromisoformat(start)
    if period=='1주': return d+timedelta(days=7)
    if period=='2주': return d+timedelta(days=14)
    y=d.year+(d.month==12); m=d.month%12+1
    return date(y,m,min(d.day,calendar.monthrange(y,m)[1]))
def advance_due(d,period):
    while d<=today(): d=next_date(d.isoformat(),period)
    return d

def refresh(message):
    st.session_state['flash']=message; st.rerun()

if st.session_state.get('demo_mode') and not setting('parent_pin'):
    with conn() as c:
        set_pin(c,'parent_pin',secrets.token_urlsafe(24))
        set_pin(c,'child_pin',secrets.token_urlsafe(24))
        put(c,'children',json.dumps(['다민','동생'],ensure_ascii=False))
        put(c,'period','1주')
        put(c,'next_due',(today()+timedelta(days=7)).isoformat())

def leave_demo():
    storage=st.session_state.pop('demo_storage',None)
    if storage is not None:
        storage.cleanup()
    for key in ['demo_mode','role','who','setup_page','flash']:
        st.session_state.pop(key,None)
    st.rerun()

st.markdown('''<style>
.stApp {background:linear-gradient(145deg,#f2faf6,#fffaf1)}
h1,h2,h3 {color:#245c46} .stButton>button {border-radius:14px;min-height:44px}
[data-testid="stMetric"] {background:white;padding:16px;border-radius:18px;border:1px solid #dcebe2}
</style>''',unsafe_allow_html=True)
st.title('🌱 성실한 다민이가 될꺼에요!')
st.caption('작은 실천을 모아 큰 자신감으로 · 우리 가족 퀘스트 통장')
if 'flash' in st.session_state: st.success(st.session_state.pop('flash'))

# 첫 화면은 가입·비밀번호 없이 두 가지 시작 버튼만 제공합니다.
if 'role' not in st.session_state:
    st.caption('어떤 역할로 시작할까요?')
    if st.button('🌱 다민, 동생으로 시작',type='primary',use_container_width=True):
        st.session_state.update(demo_mode=True,role='child',who='다민')
        st.rerun()
    if st.button('👨‍👩‍👧‍👦 부모님으로 시작',use_container_width=True):
        st.session_state.update(demo_mode=True,role='parent',who='부모님')
        st.rerun()
    st.caption('비밀번호 없는 체험용입니다. 실제 가족 기록과 분리되며, 체험을 종료하면 기록이 삭제됩니다.')
    st.stop()

def seed_example_quests(children):
    """한 번만 예시를 추가합니다. 기존 퀘스트와 적립 내역은 변경하지 않습니다."""
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute("SELECT 1 FROM settings WHERE key='example_quests_v1'").fetchone():
            return
        solo=children[0]
        examples=[
            ('방 청소하기', '바닥의 물건을 제자리에 놓고, 책상 위를 정리한 뒤 닦아요. 부모님께 확인받으면 성공!', [solo], 2000, 3),
            ('오늘 숙제 끝내기', '오늘 학교 숙제를 모두 마치고 준비물을 챙겨요. 끝낸 숙제를 부모님께 보여 주세요.', [solo], 1500, 1),
            ('책 읽기 20분', '읽고 싶은 책을 20분 읽고, 기억에 남는 내용을 부모님께 한 가지 이야기해요.', [solo], 1000, 3),
            ('식사 후 식탁 정리', '내 그릇을 싱크대에 옮기고 식탁을 닦아요. 깨지기 쉬운 그릇은 부모님 도움을 받아요.', [solo], 500, 2),
        ]
        if len(children)>=2:
            team=children[:2]
            examples.extend([
                ('함께 장보고 오기', '부모님과 함께 안전하게 장을 봐요. 한 명은 장보기 목록을 확인하고, 다른 한 명은 물건을 찾아요. 돌아와 함께 정리하면 성공! 각자 완료 버튼을 눌러 주세요.', team, 2000, 7),
                ('함께 공부 1시간', '함께 각자의 공부를 25분씩 두 번 하고, 마지막 10분은 서로 배운 내용을 이야기해요. 중간 휴식은 공부 시간에 포함하지 않아요. 각자 완료 버튼을 눌러 주세요.', team, 3000, 7),
            ])
        for title,description,participants,reward,days in examples:
            qid=c.execute('INSERT INTO quests(title,description,due,created) VALUES(?,?,?,?)',
                (title,description,(today()+timedelta(days=days)).isoformat(),now())).lastrowid
            c.executemany('INSERT INTO members(quest_id,name,reward) VALUES(?,?,?)',
                [(qid,name,reward) for name in participants])
        put(c,'example_quests_v1','1')

names=json.loads(setting('children'))
seed_example_quests(names)
if st.session_state.get('demo_mode'):
    st.info('🎮 체험 중입니다. 왼쪽 메뉴에서 부모님·아이 역할을 바꿔보세요. 체험 종료 시 체험 기록은 삭제됩니다.')
parent=st.session_state.role=='parent'; who=st.session_state.who
with st.sidebar:
    st.header('🏡 우리 가족')
    st.write(f'{who}님, 반가워요!')
    st.caption('부모님 모드' if parent else '아이 모드')
    if st.session_state.get('demo_mode'):
        st.info('🎮 체험 모드 · 실제 가족 기록과 분리되어 있습니다.')
        for label,person in [('👨‍👩‍👧‍👦','부모님'),('🌱','다민'),('🌼','동생')]:
            if st.button(label, key='demo_role_'+person,help=person+' 역할로 체험',use_container_width=True):
                st.session_state.update(role='parent' if person=='부모님' else 'child',who=person)
                st.rerun()
        if st.button('🏁 체험 종료',use_container_width=True):
            leave_demo()
    if st.button('🏠 시작 화면'):
        if st.session_state.get('demo_mode'):
            leave_demo()
        for k in ['role','who']: st.session_state.pop(k,None)
        st.rerun()
    st.info('완벽하지 않아도 괜찮아. 오늘 하나만 해보자!')

balance=query('SELECT name,SUM(amount) amount FROM ledger WHERE payout_id IS NULL GROUP BY name')
balances={r['name']:r['amount'] for r in balance}
if parent:
    cols=st.columns(len(names))
    for col,n in zip(cols,names): col.metric(f'🐷 {n}의 미정산 용돈',money(balances.get(n,0)))
else:
    a,b=st.columns(2)
    a.metric('🐷 내 미정산 용돈',money(balances.get(who,0)))
    count=query('SELECT COUNT(*) n FROM ledger WHERE name=?',(who,))[0]['n']
    b.metric('🏅 성공한 퀘스트',f'{count}개')
st.caption(f"다음 정산일: {setting('next_due')} · 주기: {setting('period')} · 승인된 퀘스트만 적립됩니다.")
# 메뉴는 간단한 이모지만 표시합니다. 완료 조건과 금액 등 필수 설명은 유지합니다.
tabs=st.tabs(['🎯','✅','➕','💰','⚙️'] if parent else ['🎯','💰','💡'])
with tabs[0]:
    status=st.radio('퀘스트 상태', ['진행 중','승인 대기','성공','취소','전체'], horizontal=True, label_visibility='collapsed', format_func=lambda x: {'진행 중':'🏃','승인 대기':'⏳','성공':'🏆','취소':'🚫','전체':'📋'}[x])
    codes={'진행 중':'open','승인 대기':'submitted','성공':'approved','취소':'cancelled'}
    sql='SELECT DISTINCT q.* FROM quests q JOIN members m ON m.quest_id=q.id WHERE 1=1'; args=[]
    if not parent: sql+=' AND m.name=?'; args.append(who)
    if status!='전체': sql+=' AND q.status=?'; args.append(codes[status])
    qs=query(sql+' ORDER BY q.id DESC',args)
    if not qs: st.info('아직 퀘스트가 없어요. 작은 목표부터 시작해 볼까요?')
    labels={'open':'도전 중','submitted':'부모님 확인 중','approved':'성공!','cancelled':'취소됨'}
    for q in qs:
        members=query('SELECT * FROM members WHERE quest_id=?',(q['id'],))
        with st.container(border=True):
            st.subheader(('🤝 ' if len(members)>1 else '🎯 ')+q['title'])
            st.caption(f"#{q['id']} · {labels[q['status']]} · 기한: {q['due'] or '없음'}")
            if q['due'] and q['due']<today().isoformat() and q['status']=='open': st.warning('기한이 지났어요. 부모님과 이야기해 보세요. 늦게 완료해도 승인 요청은 가능합니다.')
            st.write(q['description'])
            for m in members: st.write(f"{'✅' if m['done'] else '⬜'} {m['name']} · 성공 보상 {money(m['reward'])}")
            if q['note']: st.info('부모님 메시지: '+q['note'])
            if not parent and q['status']=='open':
                me=next(m for m in members if m['name']==who)
                if not me['done'] and st.button('🙌 내 역할 완료! 승인 요청하기',key=f'done{q["id"]}',type='primary'):
                    with conn() as c:
                        c.execute('BEGIN IMMEDIATE')
                        current=c.execute('SELECT status FROM quests WHERE id=?',(q['id'],)).fetchone()
                        if current['status']=='open':
                            c.execute('UPDATE members SET done=1 WHERE quest_id=? AND name=?',(q['id'],who))
                            left=c.execute('SELECT COUNT(*) FROM members WHERE quest_id=? AND done=0',(q['id'],)).fetchone()[0]
                            if left==0: c.execute("UPDATE quests SET status='submitted',submitted=? WHERE id=?",(now(),q['id']))
                    refresh('완료를 기록했어요! 팀 퀘스트는 모두 완료하면 부모님께 승인 요청됩니다.')
                elif me['done']: st.caption('내 역할은 완료! 팀원의 완료를 기다려 주세요.')
            if parent and q['status'] in ['open','submitted']:
                if st.checkbox('취소 확인',key=f'cancelcheck{q["id"]}') and st.button('이 퀘스트 취소',key=f'cancel{q["id"]}'):
                    with conn() as c: c.execute("UPDATE quests SET status='cancelled' WHERE id=? AND status IN ('open','submitted')",(q['id'],))
                    refresh('퀘스트를 취소했습니다. 적립금은 발생하지 않습니다.')

if parent:
    with tabs[1]:
        st.subheader('✅ 승인 대기함')
        st.caption('아이가 완료한 퀘스트를 확인하고 승인해 주세요. 승인한 뒤에만 용돈이 적립됩니다.')
        pending=query("SELECT * FROM quests WHERE status='submitted' ORDER BY submitted,id")
        if not pending:
            st.info('아직 승인할 퀘스트가 없어요. 아이 모드에서 완료한 뒤 이곳에서 확인해 주세요. 팀 퀘스트는 모두 완료해야 표시됩니다.')
        for q in pending:
            with st.container(border=True):
                st.subheader(q['title'])
                st.write(q['description'])
                members=query('SELECT * FROM members WHERE quest_id=?',(q['id'],))
                for m in members:
                    st.write(f"✅ {m['name']} · {money(m['reward'])}")
                note=st.text_input('칭찬 또는 다시 도전할 내용',key=f'note{q["id"]}',max_chars=500)
                a,b=st.columns(2)
                if a.button('✅ 승인하고 적립',key=f'approve{q["id"]}',type='primary'):
                    with conn() as c:
                        c.execute('BEGIN IMMEDIATE')
                        cur=c.execute("UPDATE quests SET status='approved',approved=?,note=? WHERE id=? AND status='submitted'",(now(),note,q['id']))
                        if cur.rowcount:
                            c.execute('INSERT INTO ledger(quest_id,name,amount,earned) SELECT quest_id,name,reward,? FROM members WHERE quest_id=?',(now(),q['id']))
                    refresh('참 잘했어요! 용돈이 적립되었습니다. 🎉')
                if b.button('🔁 다시 도전',key=f'return{q["id"]}'):
                    with conn() as c:
                        c.execute('BEGIN IMMEDIATE')
                        cur=c.execute("UPDATE quests SET status='open',note=?,submitted=NULL WHERE id=? AND status='submitted'",(note,q['id']))
                        if cur.rowcount: c.execute('UPDATE members SET done=0 WHERE quest_id=?',(q['id'],))
                    refresh('다시 도전할 수 있도록 돌려보냈어요.')

if parent:
    with tabs[2]:
        st.subheader('작은 행동을 구체적인 퀘스트로!')
        st.caption('예: 방 청소 2,000원 · 동생과 장보기 · 함께 공부 1시간. 보상은 각자 받는 금액입니다.')
        with st.form('newquest',clear_on_submit=True):
            title=st.text_input('퀘스트 이름',max_chars=80,placeholder='예: 방 바닥 정리하고 책상 닦기')
            desc=st.text_area('완료 조건',max_chars=1500,placeholder='예: 바닥의 물건을 제자리에 놓고, 책상 위를 닦으면 성공!')
            st.caption('함께할 아이 · 2명 이상이면 팀 퀘스트')
            selected=[n for i,n in enumerate(names) if st.checkbox(n,value=(i==0),key=f'participant_{i}')]
            # 폼 내부 선택은 제출 전 재실행되지 않으므로 보상 입력은 모든 아이에게 제공합니다.
            rewards={n:st.number_input(f'{n} 보상 (선택된 아이만 적용)',min_value=0,max_value=1000000,value=2000,step=500,key=f'reward{n}') for n in names}
            use_due=st.checkbox('마감일 사용',value=False)
            due=st.date_input('마감일',value=today()+timedelta(days=7),min_value=today())
            save=st.form_submit_button('🌟 퀘스트 등록',type='primary')
        if save:
            if not title.strip() or not desc.strip() or not selected: st.error('이름, 완료 조건, 참여자를 모두 입력해 주세요.')
            else:
                with conn() as c:
                    cur=c.execute('INSERT INTO quests(title,description,due,created) VALUES(?,?,?,?)',(title.strip(),desc.strip(),due.isoformat() if use_due else None,now()))
                    c.executemany('INSERT INTO members(quest_id,name,reward) VALUES(?,?,?)',[(cur.lastrowid,n,rewards[n]) for n in selected])
                refresh('새 퀘스트가 생겼어요!')

with tabs[3 if parent else 1]:
    st.subheader('💰 승인된 용돈 기록')
    rows=query('SELECT l.id,q.title AS 퀘스트,l.name AS 이름,l.amount AS 적립금,l.earned AS 승인일,CASE WHEN l.payout_id IS NULL THEN \'미정산\' ELSE \'지급 완료\' END AS 상태,l.payout_id AS 정산번호 FROM ledger l JOIN quests q ON q.id=l.quest_id'+('' if parent else ' WHERE l.name=?')+' ORDER BY l.id DESC',() if parent else (who,))
    if rows:
        df=pd.DataFrame(rows).drop(columns=['id'])
        st.dataframe(df,hide_index=True,use_container_width=True)
        st.download_button('내역 CSV 다운로드',df.to_csv(index=False).encode('utf-8-sig'),file_name='allowance.csv',mime='text/csv')
    else: st.info('첫 번째 성공을 기다리고 있어요!')
    if parent:
        st.divider(); st.subheader('정산 · 실제 지급 확인')
        st.warning('앱이 자동 송금하지는 않습니다. 현금이나 계좌로 지급한 뒤 아래에서 기록해 주세요. 미승인 퀘스트는 포함되지 않습니다.')
        overdue=today()>=date.fromisoformat(setting('next_due'))
        if overdue: st.info('📅 정산일이 되었어요!')
        total=sum(balances.values()); st.write('현재 미정산 합계: **'+money(total)+'**')
        paid_confirm=st.checkbox('현재 미정산된 용돈을 모두 실제로 지급했습니다.')
        if st.button('지급 완료로 기록',disabled=not paid_confirm or total<=0,type='primary'):
            with conn() as c:
                c.execute('BEGIN IMMEDIATE')
                actual=c.execute('SELECT COALESCE(SUM(amount),0) FROM ledger WHERE payout_id IS NULL').fetchone()[0]
                if actual>0:
                    pid=c.execute('INSERT INTO payouts(paid_at,total) VALUES(?,?)',(now(),actual)).lastrowid
                    c.execute('UPDATE ledger SET payout_id=? WHERE payout_id IS NULL',(pid,))
                    d=date.fromisoformat(setting('next_due'))
                    put(c,'next_due',advance_due(d,setting('period')).isoformat())
            refresh('지급 완료로 기록했습니다. 이체는 별도로 해 주세요.')
        st.caption('정산은 현재까지 승인된 미지급분 전체를 대상으로 합니다. 조기 정산 시 예정일은 유지되고, 정산일 경과 시 다음 예정일로 넘어갑니다.')
        history=query('SELECT id AS 정산번호,paid_at AS 지급일,total AS 지급합계 FROM payouts ORDER BY id DESC')
        if history: st.dataframe(pd.DataFrame(history),hide_index=True,use_container_width=True)

with tabs[4 if parent else 2]:
    if parent:
        st.subheader('📆 정산 주기')
        with st.form('schedule'):
            period=st.radio('주기',['1주','2주','1개월'],index=['1주','2주','1개월'].index(setting('period')),horizontal=True)
            due=st.date_input('다음 정산일',value=date.fromisoformat(setting('next_due')))
            if st.form_submit_button('정산 일정 저장'):
                with conn() as c: put(c,'period',period); put(c,'next_due',due.isoformat())
                refresh('정산 일정을 저장했습니다.')
        st.caption('1개월은 달력 기준입니다. 다음 달에 같은 날짜가 없으면 말일로 계산합니다.')
        st.subheader('📱 QR로 우리 가족 앱 열기')
        app_url=st.text_input('배포된 앱의 https 주소',value=secret('APP_URL'),placeholder='https://your-app.streamlit.app')
        if app_url:
            from urllib.parse import urlparse
            u=urlparse(app_url)
            if u.scheme=='https' and u.netloc and not u.username and not u.password:
                image=qrcode.make(app_url); buf=io.BytesIO(); image.save(buf,format='PNG')
                st.image(buf.getvalue(),width=220,caption='휴대폰 카메라로 스캔 → 로그인')
                st.download_button('QR 이미지 다운로드',buf.getvalue(),'family-app-qr.png','image/png')
            else: st.error('올바른 https 주소를 입력해 주세요. 비밀번호를 주소에 넣지 마세요.')
        if not st.session_state.get('demo_mode'):
            st.subheader('🔐 비밀번호 변경')
        with st.container(border=True):
            with st.form('password'):
                old=st.text_input('현재 부모님 비밀번호',type='password')
                newp=st.text_input('새 부모님 비밀번호 (변경 시 8자 이상)',type='password')
                newp2=st.text_input('새 부모님 비밀번호 확인',type='password')
                newc=st.text_input('새 아이 공용 비밀번호 (변경 시 4자 이상)',type='password')
                if st.form_submit_button('비밀번호 저장'):
                    if not check_pin('parent_pin',old): st.error('현재 비밀번호가 맞지 않습니다.')
                    elif (newp and (len(newp)<8 or newp!=newp2)) or (newc and len(newc)<4): st.error('새 비밀번호 길이와 확인을 확인해 주세요.')
                    elif not newp and not newc: st.error('변경할 비밀번호를 입력해 주세요.')
                    else:
                        with conn() as c:
                            if newp: set_pin(c,'parent_pin',newp)
                            if newc: set_pin(c,'child_pin',newc)
                        refresh('비밀번호를 변경했습니다. 이미 로그인한 다른 세션은 자동 로그아웃되지 않습니다.')
        if not st.session_state.get('demo_mode'):
            st.subheader('💾 데이터 백업·복원 (중요)')
        with st.container(border=True):
            st.warning('기본 저장소는 앱 서버의 SQLite 파일입니다. Streamlit Community Cloud에서는 재시작·재배포 시 데이터가 사라질 수 있습니다. GitHub는 실행 중 데이터의 저장소가 아닙니다. 중요한 기록은 자주 백업하고, 장기 운영은 영구 디스크가 있는 서버에서 사용하세요.')
            source=conn(); target=sqlite3.connect(':memory:')
            try:
                source.backup(target); backup=target.serialize()
            finally: source.close(); target.close()
            st.download_button('전체 DB 백업 다운로드',backup,f'damin-backup-{today()}.sqlite3','application/octet-stream')
            st.caption('백업에는 비밀번호 해시와 가족 기록이 포함됩니다. 외부에 공유하거나 GitHub에 올리지 마세요.')
            upload=st.file_uploader('이 앱에서 받은 DB 백업',type=['sqlite3','db'])
            confirm=st.checkbox('복원하면 현재 모든 기록이 백업 내용으로 교체됨을 이해합니다.')
            restore_pw=st.text_input('복원 확인용 현재 부모님 비밀번호',type='password')
            if st.button('백업으로 복원',disabled=not upload or not confirm):
                if not check_pin('parent_pin',restore_pw): st.error('현재 비밀번호를 확인해 주세요.')
                elif upload.size>20*1024*1024: st.error('20MB 이하의 백업만 지원합니다.')
                else:
                    temp=sqlite3.connect(':memory:')
                    try:
                        temp.deserialize(upload.getvalue())
                        if temp.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('손상된 DB')
                        tables={r[0] for r in temp.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                        if not {'settings','quests','members','ledger','payouts'}<=tables: raise ValueError('앱 백업이 아닙니다')
                        # 스키마·설정 검증 후 데이터만 가져옵니다. 업로드의 스키마/트리거는 실행하지 않습니다.
                        columns={'settings':['key','value'],'quests':['id','title','description','due','status','created','submitted','approved','note'],'members':['quest_id','name','reward','done'],'payouts':['id','paid_at','total'],'ledger':['id','quest_id','name','amount','earned','payout_id']}
                        data={t:temp.execute('SELECT '+','.join(cols)+' FROM '+t).fetchall() for t,cols in columns.items()}
                        settings=dict(data['settings']); kids=json.loads(settings['children'])
                        if not isinstance(kids,list) or not 1<=len(kids)<=6 or any(not isinstance(n,str) or not n or len(n)>20 for n in kids): raise ValueError('아이 정보 오류')
                        if settings['period'] not in ['1주','2주','1개월']: raise ValueError('주기 오류')
                        date.fromisoformat(settings['next_due'])
                        for key in ['parent_pin','child_pin']:
                            pin=json.loads(settings[key]); bytes.fromhex(pin['salt']); bytes.fromhex(pin['hash'])
                        with conn() as c:
                            c.execute('BEGIN IMMEDIATE')
                            for t in ['ledger','members','payouts','quests','settings']: c.execute('DELETE FROM '+t)
                            for t in ['settings','quests','members','payouts','ledger']:
                                cols=columns[t]
                                c.executemany('INSERT INTO '+t+'('+','.join(cols)+') VALUES('+','.join('?' for _ in cols)+')',data[t])
                            if c.execute('PRAGMA foreign_key_check').fetchall(): raise ValueError('데이터 연결 오류')
                        for k in ['role','who']: st.session_state.pop(k,None)
                        st.session_state['restored']=True
                    except Exception:
                        st.error('복원에 실패했습니다. 이 앱에서 다운로드한 정상 백업인지 확인해 주세요. 현재 데이터는 유지됩니다.')
                    finally: temp.close()
                    if st.session_state.pop('restored',False): refresh('복원 완료! 백업에 저장된 비밀번호로 다시 로그인해 주세요.')
        if not st.session_state.get('demo_mode'):
            st.subheader('🚀 GitHub · Streamlit 배포 안내')
        with st.container(border=True):
            st.markdown('''1. GitHub 저장소에 **app.py**와 **requirements.txt**를 올립니다.
2. Streamlit Community Cloud에서 GitHub 저장소를 연결하고 실행 파일을 **app.py**로 지정합니다.
3. 배포 설정의 Secrets에 아래 값을 넣는 것을 권장합니다. SETUP_KEY는 공개 배포 전 임의의 긴 문자열로 바꾸세요.
4. 앱을 열어 부모님이 초기 설정 후, 배포 주소를 QR 입력란에 붙여 넣습니다.
5. 가족에게 QR과 아이 비밀번호를 따로 전달합니다. 서버는 한 가족만 사용하도록 설계되었습니다.''')
            st.code('SETUP_KEY = "여기에-긴-임의의-초기설정키"\nAPP_URL = "https://your-app.streamlit.app"\n# 영구 디스크가 있는 서버만 실제 경로 지정\n# DB_PATH = "/persistent/damin.sqlite3"',language='toml')
            st.caption('비밀번호·DB·백업 파일은 GitHub에 올리지 마세요. SETUP_KEY 없이 공개하면 먼저 방문한 사람이 가족 설정을 할 수 있습니다. 기본 비밀번호 복구 기능은 없으므로 안전하게 보관하세요.')
    st.subheader('💡 사용 팁')
    st.markdown('''- **한 번에 작은 목표 하나**: “방 청소” 대신 “바닥 정리 5분”처럼 시작해요.
- **팀플은 모두 완료**: 참여자 모두 완료 버튼을 눌러야 승인 요청이 됩니다.
- **부모님 승인 후 적립**: 승인 전에는 용돈이 늘어나지 않아요.
- **보상은 각자 금액**: 팀 보상 2,000원씩이면 두 명 합계는 4,000원이에요.
- **QR은 입장권이 아닌 접속 링크**: 스캔 후에도 비밀번호가 필요해요.
- 실제 돈의 지급과 부모님 확인은 가족끼리 진행해 주세요.''')
    st.caption('이 앱은 가족용 소규모 도구입니다. 아이 공용 비밀번호, 세션별 로그인 제한을 사용하며 금융 서비스 수준의 인증·감사·보안을 제공하지 않습니다. 여러 가족이 함께 쓰는 공개 서비스에는 별도 인증과 영구 DB 설계가 필요합니다.')
