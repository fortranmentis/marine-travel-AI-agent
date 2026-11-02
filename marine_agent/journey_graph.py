"""Bounded journey graph. Only structured trip/plan state reaches checkpoints."""
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from . import planner, progress, regions

class State(TypedDict, total=False):
    trip: dict
    plan: dict
    attempts: int
    accepted: bool
    use_ai: bool
    answer: str
    model_status: str
    trace: list
    choices: list[str]
    needs_choice: bool

def build(state):
    from . import agent
    trip=planner.Trip.model_validate(state['trip'])  # also rechecks dates on resume
    progress.emit('schedule','최신 자료로 여행 조건을 다시 검토하고 있어요.',event='tool',tool='journey_build')
    answer='최신 자료와 일정 규칙으로 초안을 검토했습니다.'
    trace=[];model_status='rules';plan=None
    if state.get('use_ai') and not state.get('attempts'):
        response=agent.chat('입력한 여행 조건을 유지해 검토용 일정을 만들고 적용 규칙과 미확인 사항을 설명해 주세요.',trip=trip)
        plan=response.get('plan');answer=response.get('answer',answer)
        trace=response.get('trace',[]);model_status=response.get('status','degraded')
    if plan is None:plan=planner.build_plan(trip)
    if state.get('attempts'):
        answer='선택한 조건과 최신 예보로 다시 검토했습니다. 변경된 방문 수·이동수단·확인사항을 일정 카드에서 확인하세요.'
    progress.emit('schedule','일정 구성을 마쳤어요.',event='tool',tool='journey_build',state='completed')
    return dict(plan=plan,attempts=state.get('attempts',0)+1,answer=answer,trace=trace,model_status=model_status)

def validate(state):
    from .mobility import capabilities
    progress.emit('schedule','날씨와 방문 수 부족의 관계를 검증하고 있어요.',event='tool',tool='journey_validate')
    need=any(d['actual_visits']<d['requested_visits'] and any(x['code'] in ('rain','rain_indoor_required','wind_indoor_required','walk_budget')
             for x in d.get('rule_summary',{}).get('decisions',[])) for d in state['plan']['days'])
    trip=state['trip'];choices=['keep']
    if trip.get('visits_per_day',2)>1:choices.append('fewer')
    if trip.get('transport')=='walk' and not trip.get('island_id') and regions.get(trip['region']).get('planning_mode')!='island_draft' and capabilities()['transit']:
        choices.append('transit')
    progress.emit('schedule','검증을 마쳤어요.',event='tool',tool='journey_validate',state='completed')
    return dict(needs_choice=need and not state.get('accepted') and state['attempts']<3,choices=choices)

def choose(state):
    # This node replays from the beginning on resume: keep side effects outside it.
    choice=interrupt(dict(question='날씨·이동 조건으로 방문 수가 줄었습니다. 어떻게 진행할까요?',options=state['choices'],
                          attempts=state['attempts'],max_replans=2))
    if choice not in state['choices']:raise ValueError('지원하지 않는 선택입니다.')
    from .mobility import capabilities
    if choice=='transit' and not capabilities()['transit']:raise ValueError('대중교통 조회 연결을 확인해 주세요.')
    trip=dict(state['trip'])
    if choice=='transit':trip['transport']='transit'
    elif choice=='fewer':trip['visits_per_day']=max(1,trip.get('visits_per_day',2)-1)
    progress.emit('schedule','사용자의 선택을 반영했어요.',event='tool',tool='journey_decision',state='completed')
    return dict(trip=trip,accepted=choice=='keep')

def finish(state):
    progress.emit('schedule','검토 결과를 준비했어요.',event='tool',tool='journey_finish',state='completed')
    return dict(needs_choice=False)

def graph(checkpointer):
    g=StateGraph(State)
    for name,node in [('build',build),('validate',validate),('choose',choose),('finish',finish)]:g.add_node(name,node)
    g.add_edge(START,'build');g.add_edge('build','validate')
    g.add_conditional_edges('validate',lambda s:'choose' if s['needs_choice'] else 'finish')
    g.add_edge('choose','build');g.add_edge('finish',END)
    return g.compile(checkpointer=checkpointer)
