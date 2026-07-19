import json
from .json_tools import extract_json

class LearningGenerationService:
    def __init__(self,provider,repository): self.provider=provider; self.repo=repository
    def _call(self,instructions,text,tokens,metadata):
        r=self.provider.complete_custom(instructions=instructions,text=text,max_output_tokens=tokens,metadata=metadata)
        if r.error or not r.text: raise RuntimeError(r.error or 'Порожня відповідь OpenAI')
        return extract_json(r.text)
    def generate_curriculum(self,user_id,subject,goal,level='basic',force=False):
        cached=self.repo.get_curriculum(user_id,subject,goal,level)
        if cached and not force:return self.repo.curriculum_bundle(cached['id'],user_id)
        d=self._call('Ти методист EasyNMT v1.0 Beta. Поверни ТІЛЬКИ JSON: {"title":str,"summary":str,"topics":[{"title":str,"description":str,"objectives":[str],"prerequisites":[str],"difficulty":"basic|medium|advanced","estimated_minutes":int}]}. 12-24 послідовні теми, від основ до складного, без повторів.',f'Предмет: {subject}\nЦіль: {goal}\nРівень: {level}',6000,{'task':'curriculum'})
        if not isinstance(d,dict) or not isinstance(d.get('topics'),list) or not 5<=len(d['topics'])<=30: raise ValueError('Некоректна програма від AI')
        cid=self.repo.save_curriculum(user_id,subject,goal,level,d); return self.repo.curriculum_bundle(cid,user_id)
    def generate_lesson(self,user_id,topic_id,force=False):
        t=self.repo.topic(topic_id,user_id)
        if not t: raise ValueError('Тему не знайдено')
        c=self.repo.cached_lesson(topic_id)
        if c and not force:return c
        d=self._call('Ти живий український репетитор EasyNMT v1.0 Beta. Поверни ТІЛЬКИ JSON: {"title":str,"goals":[str],"nmt_relevance":str,"warmup":str,"theory":[{"heading":str,"explanation":str,"formula":str}],"worked_example":{"problem":str,"steps":[str],"answer":str},"common_mistakes":[{"mistake":str,"fix":str}],"mini_practice":[{"question":str,"hint":str,"answer":str}],"recap":[str],"quality_score":number}. Пояснюй природно та достатньо для тесту.',f"Предмет: {t['subject']}\nТема: {t['title']}\nОпис: {t['description']}\nЦіль: {t['goal']}\nРівень: {t['level']}",6500,{'task':'lesson','topic_id':str(topic_id)})
        if not all(k in d for k in ['title','goals','theory','worked_example','common_mistakes','recap']): raise ValueError('Некоректний урок від AI')
        self.repo.save_lesson(topic_id,d,getattr(self.provider,'model','')); return self.repo.cached_lesson(topic_id)
    def generate_quiz(self,user_id,topic_id,force=False):
        t=self.repo.topic(topic_id,user_id)
        if not t: raise ValueError('Тему не знайдено')
        lesson=self.generate_lesson(user_id,topic_id)
        c=self.repo.cached_quiz(topic_id)
        if c and not force:return c
        d=self._call('Ти конструктор тестів EasyNMT v1.0 Beta. Поверни ТІЛЬКИ JSON: {"title":str,"pass_score":18,"max_score":24,"questions":[...]}. Рівно 12 питань. 1-4 type=mcq, 1 бал, options рівно 4, correct_answer A-D. 5-8 type=short, 2 бали, answer і rubric. 9-12 type=solution, 3 бали, answer, solution_steps і rubric. Лише за матеріалом уроку.',f"Тема: {t['title']}\nУрок: {json.dumps(lesson['content'],ensure_ascii=False)}",7000,{'task':'quiz','topic_id':str(topic_id)})
        q=d.get('questions') if isinstance(d,dict) else None
        if not isinstance(q,list) or len(q)!=12: raise ValueError('AI має створити рівно 12 питань')
        exp=['mcq']*4+['short']*4+['solution']*4
        for i,(item,typ) in enumerate(zip(q,exp),1):
            if item.get('type')!=typ: raise ValueError(f'Неправильний тип питання {i}')
            item['number']=i; item['points']=1 if i<=4 else 2 if i<=8 else 3
        self.repo.save_quiz(topic_id,d,getattr(self.provider,'model','')); return self.repo.cached_quiz(topic_id)
    def grade_quiz(self,user_id,quiz_id,answers):
        c=self.repo.connect(); row=c.execute('SELECT * FROM ai_generated_quizzes WHERE id=?',(quiz_id,)).fetchone(); c.close()
        if not row: raise ValueError('Тест не знайдено')
        questions=json.loads(row['questions_json'])
        d=self._call('Ти точний доброзичливий перевіряльник EasyNMT. Поверни ТІЛЬКИ JSON: {"score":int,"max_score":24,"pass_score":18,"passed":bool,"items":[{"number":int,"score":int,"max_score":int,"is_correct":bool,"feedback":str,"mistake_step":str,"correct_solution":str}],"summary":str,"weak_points":[str],"next_action":str}. Давай часткові бали за рубрикою.',f'Питання: {json.dumps(questions,ensure_ascii=False)}\nВідповіді: {json.dumps(answers,ensure_ascii=False)}',7000,{'task':'grading','quiz_id':str(quiz_id)})
        d['max_score']=24; d['pass_score']=18; d['passed']=int(d.get('score',0))>=18
        self.repo.save_grade(user_id,quiz_id,answers,d); return d
