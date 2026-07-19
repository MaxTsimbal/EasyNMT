import json, sqlite3
from datetime import datetime, timezone

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')

class LearningRepository:
    def __init__(self, db_path): self.db_path=db_path
    def connect(self):
        c=sqlite3.connect(self.db_path,timeout=30); c.row_factory=sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON'); c.execute('PRAGMA busy_timeout=30000'); c.execute('PRAGMA journal_mode=WAL')
        return c
    def ensure_schema(self):
        c=self.connect(); c.executescript("""
        CREATE TABLE IF NOT EXISTS ai_curricula(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,subject TEXT NOT NULL,goal TEXT NOT NULL,level TEXT NOT NULL DEFAULT 'basic',title TEXT NOT NULL,summary TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'active',version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(user_id,subject,goal,level),FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS ai_topics(id INTEGER PRIMARY KEY AUTOINCREMENT,curriculum_id INTEGER NOT NULL,position INTEGER NOT NULL,title TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',objectives_json TEXT NOT NULL DEFAULT '[]',prerequisites_json TEXT NOT NULL DEFAULT '[]',difficulty TEXT NOT NULL DEFAULT 'basic',estimated_minutes INTEGER NOT NULL DEFAULT 45,status TEXT NOT NULL DEFAULT 'locked',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(curriculum_id,position),FOREIGN KEY(curriculum_id) REFERENCES ai_curricula(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS ai_generated_lessons(id INTEGER PRIMARY KEY AUTOINCREMENT,topic_id INTEGER NOT NULL UNIQUE,title TEXT NOT NULL,content_json TEXT NOT NULL,quality_score REAL NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'ready',model TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(topic_id) REFERENCES ai_topics(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS ai_generated_quizzes(id INTEGER PRIMARY KEY AUTOINCREMENT,topic_id INTEGER NOT NULL UNIQUE,title TEXT NOT NULL,questions_json TEXT NOT NULL,pass_score INTEGER NOT NULL DEFAULT 18,max_score INTEGER NOT NULL DEFAULT 24,status TEXT NOT NULL DEFAULT 'ready',model TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,FOREIGN KEY(topic_id) REFERENCES ai_topics(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS ai_grading_results(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,quiz_id INTEGER NOT NULL,answers_json TEXT NOT NULL,result_json TEXT NOT NULL,score INTEGER NOT NULL,max_score INTEGER NOT NULL,passed INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,FOREIGN KEY(quiz_id) REFERENCES ai_generated_quizzes(id) ON DELETE CASCADE);
        CREATE INDEX IF NOT EXISTS idx_ai_topics_curriculum ON ai_topics(curriculum_id,position);
        CREATE INDEX IF NOT EXISTS idx_ai_grading_user ON ai_grading_results(user_id,created_at DESC);
        """); c.commit(); c.close()
    def get_curriculum(self,user_id,subject,goal,level):
        c=self.connect(); r=c.execute('SELECT * FROM ai_curricula WHERE user_id=? AND subject=? AND goal=? AND level=?',(user_id,subject,goal,level)).fetchone(); c.close(); return dict(r) if r else None
    def save_curriculum(self,user_id,subject,goal,level,data):
        t=now(); c=self.connect()
        try:
            c.execute("""INSERT INTO ai_curricula(user_id,subject,goal,level,title,summary,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(user_id,subject,goal,level) DO UPDATE SET title=excluded.title,summary=excluded.summary,version=ai_curricula.version+1,updated_at=excluded.updated_at""",(user_id,subject,goal,level,data['title'],data.get('summary',''),t,t))
            cid=c.execute('SELECT id FROM ai_curricula WHERE user_id=? AND subject=? AND goal=? AND level=?',(user_id,subject,goal,level)).fetchone()['id']
            c.execute('DELETE FROM ai_topics WHERE curriculum_id=?',(cid,))
            for i,topic in enumerate(data['topics'],1):
                c.execute("""INSERT INTO ai_topics(curriculum_id,position,title,description,objectives_json,prerequisites_json,difficulty,estimated_minutes,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(cid,i,topic['title'],topic.get('description',''),json.dumps(topic.get('objectives',[]),ensure_ascii=False),json.dumps(topic.get('prerequisites',[]),ensure_ascii=False),topic.get('difficulty','basic'),int(topic.get('estimated_minutes',45)),'available' if i==1 else 'locked',t,t))
            c.commit(); return cid
        except: c.rollback(); raise
        finally:c.close()
    def curriculum_bundle(self,cid,user_id):
        c=self.connect(); cur=c.execute('SELECT * FROM ai_curricula WHERE id=? AND user_id=?',(cid,user_id)).fetchone(); topics=c.execute('SELECT * FROM ai_topics WHERE curriculum_id=? ORDER BY position',(cid,)).fetchall(); c.close()
        if not cur:return None
        out=dict(cur); out['topics']=[{**dict(x),'objectives':json.loads(x['objectives_json']),'prerequisites':json.loads(x['prerequisites_json'])} for x in topics]; return out
    def topic(self,topic_id,user_id):
        c=self.connect(); r=c.execute('SELECT t.*,c.user_id,c.subject,c.goal,c.level FROM ai_topics t JOIN ai_curricula c ON c.id=t.curriculum_id WHERE t.id=? AND c.user_id=?',(topic_id,user_id)).fetchone(); c.close(); return dict(r) if r else None
    def _cached(self,table,col,topic_id):
        c=self.connect(); r=c.execute(f'SELECT * FROM {table} WHERE topic_id=?',(topic_id,)).fetchone(); c.close()
        if not r:return None
        d=dict(r); d['content' if table.endswith('lessons') else 'questions']=json.loads(d[col]); return d
    def cached_lesson(self,topic_id): return self._cached('ai_generated_lessons','content_json',topic_id)
    def cached_quiz(self,topic_id): return self._cached('ai_generated_quizzes','questions_json',topic_id)
    def save_lesson(self,topic_id,data,model):
        t=now(); c=self.connect(); payload=json.dumps(data,ensure_ascii=False)
        try:c.execute("""INSERT INTO ai_generated_lessons(topic_id,title,content_json,quality_score,model,created_at,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(topic_id) DO UPDATE SET title=excluded.title,content_json=excluded.content_json,quality_score=excluded.quality_score,model=excluded.model,updated_at=excluded.updated_at""",(topic_id,data.get('title','Урок'),payload,float(data.get('quality_score',0)),model,t,t)); c.commit()
        except:c.rollback();raise
        finally:c.close()
    def save_quiz(self,topic_id,data,model):
        t=now(); c=self.connect(); payload=json.dumps(data.get('questions',[]),ensure_ascii=False)
        try:c.execute("""INSERT INTO ai_generated_quizzes(topic_id,title,questions_json,pass_score,max_score,model,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(topic_id) DO UPDATE SET title=excluded.title,questions_json=excluded.questions_json,pass_score=excluded.pass_score,max_score=excluded.max_score,model=excluded.model,updated_at=excluded.updated_at""",(topic_id,data.get('title','Тест'),payload,int(data.get('pass_score',18)),int(data.get('max_score',24)),model,t,t)); c.commit()
        except:c.rollback();raise
        finally:c.close()
    def save_grade(self,user_id,quiz_id,answers,result):
        c=self.connect(); t=now(); score=int(result.get('score',0)); maxs=int(result.get('max_score',24)); passed=int(score>=int(result.get('pass_score',18)))
        try:c.execute('INSERT INTO ai_grading_results(user_id,quiz_id,answers_json,result_json,score,max_score,passed,created_at) VALUES(?,?,?,?,?,?,?,?)',(user_id,quiz_id,json.dumps(answers,ensure_ascii=False),json.dumps(result,ensure_ascii=False),score,maxs,passed,t)); c.commit()
        except:c.rollback();raise
        finally:c.close()
