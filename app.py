import os
import io
from PIL import Image
from pathlib import Path
import sqlite3
import secrets
import hashlib
import hmac
from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit as st

st.set_page_config(page_title="질문 있습니다!", page_icon="🎓", layout="centered")
DB = os.environ.get("QA_DB_PATH", "lecture_qa.sqlite3")
KEYWORDS = [ "동기부여", "의사결정", "강의 내용", "과제·평가", "기타"]

def connect():
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute('''CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, course TEXT NOT NULL,
        keyword TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
        context TEXT NOT NULL, answer TEXT DEFAULT '', pinned INTEGER DEFAULT 0,
        salt TEXT NOT NULL, digest TEXT NOT NULL, created TEXT NOT NULL)''')
    columns = {r[1] for r in c.execute("PRAGMA table_info(questions)")}
    if "author" not in columns:
        c.execute("ALTER TABLE questions ADD COLUMN author TEXT NOT NULL DEFAULT '익명'")
    for col, definition in [("attachment_name", "TEXT NOT NULL DEFAULT ''"), ("attachment_data", "BLOB"), ("answer_image", "BLOB")]:
        if col not in columns:
            c.execute(f"ALTER TABLE questions ADD COLUMN {col} {definition}")
    c.execute("UPDATE questions SET keyword='기타' WHERE keyword IN ('리더십','조직·팀','조직','팀')")
    c.execute("CREATE TABLE IF NOT EXISTS reactions (question_id INTEGER NOT NULL, visitor TEXT NOT NULL, PRIMARY KEY(question_id,visitor))")
    c.commit()
    return c

def stamp():
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M")

def digest(code, salt):
    return hashlib.pbkdf2_hmac("sha256", code.encode(), bytes.fromhex(salt), 150000).hex()

def add_question(keyword, body, code, author="익명", attachment=None):
    salt = secrets.token_hex(16)
    with connect() as c:
        cur = c.execute("INSERT INTO questions(course,keyword,title,body,context,salt,digest,created,author) VALUES(?,?,?,?,?,?,?,?,?)",
                        ("전용 게시판", keyword, "", body, "", salt, digest(code,salt), stamp(), author))
        if attachment is not None:
            filename = attachment.name.replace("\\", "/").split("/")[-1]
            data = attachment.getvalue()
            if Path(filename).suffix.lower() not in {".pdf", ".png", ".jpg", ".jpeg", ".docx", ".pptx", ".xlsx", ".txt", ".hwpx", ".hwp"} or len(data) > 10 * 1024 * 1024:
                raise ValueError("첨부파일 형식 또는 용량을 확인하세요. 최대 10MB입니다.")
            c.execute("UPDATE questions SET attachment_name=?,attachment_data=? WHERE id=?", (filename, data, cur.lastrowid))
        return cur.lastrowid

def remove_question(qid, code):
    with connect() as c:
        row = c.execute("SELECT salt,digest FROM questions WHERE id=?", (qid,)).fetchone()
        if row and hmac.compare_digest(digest(code,row['salt']), row['digest']):
            c.execute("DELETE FROM questions WHERE id=?", (qid,))
            return True
    return False

def toggle_reaction(qid, visitor):
    with connect() as c:
        if not c.execute("SELECT 1 FROM questions WHERE id=?", (qid,)).fetchone():
            return
        found = c.execute("SELECT 1 FROM reactions WHERE question_id=? AND visitor=?", (qid,visitor)).fetchone()
        if found:
            c.execute("DELETE FROM reactions WHERE question_id=? AND visitor=?", (qid,visitor))
        else:
            c.execute("INSERT OR IGNORE INTO reactions VALUES (?,?)", (qid,visitor))

def checked_image(upload):
    data = upload.getvalue()
    if len(data) > 10 * 1024 * 1024:
        raise ValueError("사진은 10MB 이하로 올려주세요.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
    except Exception as exc:
        raise ValueError("정상적인 사진 파일을 선택해 주세요.") from exc
    return data

def secret_value(key, default=""):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default

st.markdown('''<style>
.stApp {background:#f5f7fb;color:#172c49;}
.block-container {max-width:960px;padding-top:2rem;padding-bottom:3rem;}
h1,h2,h3 {color:#142d50 !important;letter-spacing:-.6px;}
[data-testid="stVerticalBlockBorderWrapper"] {background:#fff;border-radius:16px;border-color:#dce3ef;}
.stButton>button,.stFormSubmitButton>button {border-radius:10px;min-height:44px;font-weight:600;}
button[kind="primary"],button[kind="primaryFormSubmit"] {background:#16345b !important;color:white !important;border-color:#16345b !important;}
button[kind="secondary"] {background:white;color:#16345b;border:1px solid #cbd6e6;}
[data-baseweb="tab-list"] {border-bottom:1px solid #dce3ef;gap:8px;}
[data-baseweb="tab"] {color:#25436b;}
[data-baseweb="tab-highlight"] {background:#16345b !important;}
[data-testid="stExpander"] {background:white;border-radius:12px;}
textarea {resize:none !important;}
input,textarea {color:#172c49 !important;}
.home-mark {width:88px;height:88px;margin:0 auto 24px;background:#16345b;border-radius:24px;display:flex;align-items:center;justify-content:center;color:white;font-size:43px;font-weight:600;}
.home-title {text-align:center;font-size:clamp(36px,7vw,48px);font-weight:750;color:#142d50;letter-spacing:-2px;margin:0 0 32px;}
@media(max-width:600px){.block-container{padding-left:1rem;padding-right:1rem;}}
</style>''', unsafe_allow_html=True)

if "visitor" not in st.session_state:
    st.session_state.visitor = secrets.token_hex(24)
if "question_form_version" not in st.session_state:
    st.session_state.question_form_version = 0
if st.session_state.pop("question_posted", False):
    st.success("질문 등록되었습니다")

if "page" not in st.session_state:
    st.session_state.page = "home"
if "admin" not in st.session_state:
    st.session_state.admin = False

if st.session_state.page == "home":
    st.markdown('<div style="height:12vh"></div><div class="home-mark" aria-label="학사모 아이콘">🎓</div><div class="home-title">질문 있습니다!</div>', unsafe_allow_html=True)
    _, center, _ = st.columns([1, 2, 1])
    with center:
        if st.button("학생으로 질문하기", type="primary", use_container_width=True):
            st.session_state.admin = False
            st.session_state.page = "board"
            st.rerun()
        if st.button("교수자 로그인", use_container_width=True):
            st.session_state.page = "login"
            st.rerun()
    st.stop()

if st.session_state.page == "login":
    st.title("🎓 질문 있습니다!")
    st.subheader("교수자 로그인")
    password = secret_value("ADMIN_PASSWORD")
    if not password:
        st.info('교수자 로그인을 사용하려면 배포 설정 Secrets에 ADMIN_PASSWORD를 등록하세요. 기본 비밀번호는 없습니다.')
    else:
        with st.form("login"):
            entry = st.text_input("교수자 비밀번호", type="password")
            login = st.form_submit_button("로그인", type="primary")
        if login:
            if hmac.compare_digest(entry.encode(), str(password).encode()):
                st.session_state.admin = True
                st.session_state.page = "board"
                st.rerun()
            else:
                st.error("비밀번호가 일치하지 않습니다.")
    if st.button("홈으로"):
        st.session_state.page = "home"
        st.rerun()
    st.stop()

if st.session_state.admin and not secret_value("ADMIN_PASSWORD"):
    st.session_state.admin = False

left,right = st.columns([4,1])
left.title("🎓 질문 있습니다!")
if right.button("로그아웃" if st.session_state.admin else "홈으로"):
    st.session_state.admin = False
    st.session_state.page = "home"
    st.rerun()
st.caption("교수자 화면 · 질문을 확인하고 답변해 주세요." if st.session_state.admin else "학생 화면 · 익명 또는 이름 공개로 질문을 남겨주세요.")

if not st.session_state.admin:
    with st.container(border=True):
        st.subheader("질문하기")
        st.caption("질문은 공개됩니다. 군사·비공개 자료나 타인의 개인정보는 올리지 마세요. 이름 공개 시 입력한 이름도 게시판에 표시됩니다.")
        mode = st.radio("작성자 표시", ["익명", "이름 공개"], horizontal=True)
        with st.form("new_question_" + str(st.session_state.question_form_version), clear_on_submit=False):
            name = st.text_input("공개할 이름", max_chars=40) if mode == "이름 공개" else ""
            keyword = st.selectbox("키워드", KEYWORDS)
            body = st.text_area("질문", max_chars=3000, placeholder="궁금한 내용을 적어주세요. 필요한 경우 주차나 교재 쪽수도 함께 적어주세요.")
            attachment = st.file_uploader("자료 첨부 (선택 · 1개, 최대 10MB)", type=["pdf", "png", "jpg", "jpeg", "docx", "pptx", "xlsx", "txt", "hwpx", "hwp"], help="첨부자료도 게시판 이용자에게 공개됩니다. 개인정보와 파일 작성자 정보에 주의하세요.")
            code = st.text_input("삭제용 암호 (6자 이상)", type="password", max_chars=100, help="다른 곳에서 쓰는 비밀번호는 피하세요. 분실하면 본인이 직접 삭제할 수 없습니다.")
            submitted = st.form_submit_button("질문 등록", type="primary")
        if submitted:
            if not body.strip() or len(code.strip()) < 6 or (mode == "이름 공개" and not name.strip()):
                st.error("질문과 6자 이상 삭제 암호를 입력해 주세요. 이름 공개를 선택했다면 이름도 필요합니다.")
            elif attachment is not None and attachment.size > 10 * 1024 * 1024:
                st.error("첨부파일은 10MB 이하로 올려주세요.")
            else:
                try:
                    add_question(keyword, body.strip(), code, name.strip() if mode == "이름 공개" else "익명", attachment)
                    st.session_state.question_form_version += 1
                    st.session_state.question_posted = True
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    

@st.fragment(run_every=None if st.session_state.admin else "15s")
def question_board():
    with connect() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM questions ORDER BY pinned DESC,id DESC")]
    st.caption(f"질문 {len(rows)}개")
    
    # Each keyword has a separate board; two-column cards resemble a sticky-note board.
    for tab, kw in zip(st.tabs(["전체"]+KEYWORDS), [None]+KEYWORDS):
        with tab:
            selected = [r for r in rows if kw is None or r['keyword']==kw]
            if not selected:
                st.info("아직 등록된 질문이 없습니다." if st.session_state.admin else "아직 질문이 없습니다. 첫 질문을 남겨보세요.")
            cols = st.columns(1)
            for i, q in enumerate(selected):
                prefix = f"{kw or 'all'}_{q['id']}"
                with cols[0]:
                    with st.container(border=True):
                        st.caption(f"{'📌 ' if q['pinned'] else ''}{q['keyword']} · {q['created']}")
                        st.caption("작성자: " + q['author'])
                        if q['title']:
                            st.text(q['title'])  # 이전 버전 질문 제목 보존
                        st.text(q['body'])
                        if q.get('attachment_data') is not None:
                            st.download_button("📎 " + q['attachment_name'], data=bytes(q['attachment_data']), file_name=q['attachment_name'], mime="application/octet-stream", key="attachment_"+prefix)
                        if q['context']:
                            st.caption("수업 맥락: "+q['context'])
                        if q['answer'].strip():
                            st.markdown("**교수님 답변**")
                            st.text(q['answer'])
                        if q.get('answer_image') is not None:
                            st.image(bytes(q['answer_image']), caption="교수님 첨부 사진")
                        if not st.session_state.admin:
                            with connect() as c:
                                count = c.execute("SELECT COUNT(*) FROM reactions WHERE question_id=?", (q['id'],)).fetchone()[0]
                                liked = c.execute("SELECT 1 FROM reactions WHERE question_id=? AND visitor=?", (q['id'], st.session_state.visitor)).fetchone() is not None
                            if st.button(f"{'✓ ' if liked else ''}👍 저도 궁금해요 · {count}", key="react_"+prefix):
                                toggle_reaction(q['id'], st.session_state.visitor)
                                st.rerun(scope="fragment")
                        else:
                            with st.form("answer_"+prefix):
                                answer = st.text_area("답변", value=q['answer'], height=110, max_chars=6000)
                                answer_photo = st.file_uploader("사진 첨부 (선택)", type=["png","jpg","jpeg","webp"], key="answer_photo_"+prefix)
                                save = st.form_submit_button("답변 저장", type="primary")
                            if save:
                                try:
                                    photo = checked_image(answer_photo) if answer_photo is not None else q.get('answer_image')
                                    with connect() as c:
                                        c.execute("UPDATE questions SET answer=?,answer_image=? WHERE id=?", (answer,photo,q['id']))
                                    st.rerun()
                                except ValueError as exc:
                                    st.error(str(exc))


question_board()
